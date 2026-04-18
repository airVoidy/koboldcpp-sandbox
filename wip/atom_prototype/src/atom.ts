/**
 * Universal Atom — minimum viable shape for experimentation.
 *
 * An atom takes an input scope, applies an operation, produces an output scope.
 * That's it. Everything else is a usage mode of this primitive:
 *   - container mode: inScope = existing list, op = noop, outScope = tagged ref
 *   - projection mode: inScope = source refs, op = transform, outScope = derived view
 *   - exec mode: inScope = command args, op = side-effectful action, outScope = result
 *
 * Wrappers decorate atoms without changing identity (L2 wrapping layer).
 */

export type AtomRef = string

export type AtomKind = 'container' | 'op' | 'projection' | 'shadow' | 'group'

export type OpSpec =
  | { type: 'noop' }
  | { type: 'lambda'; fn: (input: unknown) => unknown | Promise<unknown> }
  | { type: 'named'; name: string; args?: unknown }

export interface Atom {
  id: string
  ref?: AtomRef
  kind: AtomKind
  inScope: AtomRef[]
  op?: OpSpec
  outScope: AtomRef[]
  payload?: unknown
  tags: string[]
  wrappers: string[] // wrapper ids attached to this atom
}

export interface AtomRunResult {
  atomId: string
  inputs: unknown[]
  output: unknown
  durationMs: number
  at: number
  /** Optional trace from wrappers: ordered list of (wrapperId, event, note). */
  trace?: WrapperTraceEntry[]
}

export type AtomLogger = (result: AtomRunResult) => void

/**
 * Wrapper = decorator that intercepts atom execution.
 * Does NOT change the atom's id or op spec — only wraps execution.
 *
 * Shape is "around" middleware: each wrapper receives the context and MUST
 * call next() to proceed. Order: wrappers declared earlier run outermost.
 */
export interface AtomWrapper {
  id: string
  /** Atom id to wrap. Use '*' to wrap every atom. */
  wraps: string
  /** The decorating function. Must call next() to proceed. */
  fn: (ctx: WrapperContext, next: () => Promise<unknown>) => Promise<unknown>
}

export interface WrapperContext {
  atom: Atom
  inputs: unknown[]
  /** Scratch space for wrappers to stash intermediate state. */
  scratch: Record<string, unknown>
  /** Append a trace entry visible in AtomRunResult.trace. */
  trace: (event: string, note?: unknown) => void
}

export interface WrapperTraceEntry {
  wrapperId: string
  event: string
  note?: unknown
  tAt: number
}

/**
 * Tiny registry for resolving atoms + values they produce + wrappers.
 */
export class AtomRegistry {
  private atoms = new Map<string, Atom>()
  private values = new Map<AtomRef, unknown>()
  private wrappers: AtomWrapper[] = []
  private logger: AtomLogger | null = null

  register(atom: Atom): void {
    this.atoms.set(atom.id, atom)
  }

  registerWrapper(wrapper: AtomWrapper): void {
    this.wrappers.push(wrapper)
  }

  setValue(ref: AtomRef, value: unknown): void {
    this.values.set(ref, value)
  }

  getValue(ref: AtomRef): unknown {
    return this.values.get(ref)
  }

  onRun(logger: AtomLogger): void {
    this.logger = logger
  }

  /**
   * Run an atom by id. Resolves inScope refs, applies wrappers + op,
   * writes output to every outScope ref, returns the output value.
   */
  async run(atomId: string): Promise<unknown> {
    const atom = this.atoms.get(atomId)
    if (!atom) throw new Error(`atom ${atomId} not registered`)

    const inputs = atom.inScope.map((ref) => this.values.get(ref))
    const start = performance.now()

    const traceEntries: WrapperTraceEntry[] = []
    const ctx: WrapperContext = {
      atom,
      inputs,
      scratch: {},
      trace: (event, note) => {
        traceEntries.push({ wrapperId: currentWrapperId, event, note, tAt: performance.now() - start })
      },
    }

    // Resolve wrapper chain: global wrappers ('*') + atom-specific + atom.wrappers refs
    const chain = this.resolveWrapperChain(atom)

    let currentWrapperId = '(core)'
    const output = await this.runThroughChain(chain, ctx, () => {
      currentWrapperId = '(op)'
      return this.applyOp(atom.op, inputs)
    }, (id) => {
      currentWrapperId = id
    })

    const durationMs = performance.now() - start
    for (const ref of atom.outScope) {
      this.values.set(ref, output)
    }

    const result: AtomRunResult = {
      atomId: atom.id,
      inputs,
      output,
      durationMs,
      at: Date.now(),
      trace: traceEntries.length > 0 ? traceEntries : undefined,
    }
    this.logger?.(result)
    return output
  }

  private resolveWrapperChain(atom: Atom): AtomWrapper[] {
    return this.wrappers.filter(
      (w) => w.wraps === '*' || w.wraps === atom.id || atom.wrappers.includes(w.id),
    )
  }

  private async runThroughChain(
    chain: AtomWrapper[],
    ctx: WrapperContext,
    coreFn: () => Promise<unknown>,
    setCurrent: (id: string) => void,
  ): Promise<unknown> {
    if (chain.length === 0) return coreFn()

    // Build nested closures: wrappers[0]( ctx, () => wrappers[1]( ctx, () => ... coreFn() ) )
    let next: () => Promise<unknown> = coreFn
    for (let i = chain.length - 1; i >= 0; i--) {
      const w = chain[i]
      const prev = next
      next = async () => {
        setCurrent(w.id)
        return w.fn(ctx, prev)
      }
    }
    return next()
  }

  private async applyOp(op: OpSpec | undefined, inputs: unknown[]): Promise<unknown> {
    if (!op || op.type === 'noop') return inputs
    if (op.type === 'lambda') return op.fn(inputs.length === 1 ? inputs[0] : inputs)
    if (op.type === 'named') {
      throw new Error(`named op "${op.name}" requires a handler registry (not yet wired)`)
    }
    const never: never = op
    throw new Error(`unknown op kind: ${JSON.stringify(never)}`)
  }
}

/**
 * Convenience constructor.
 */
export function mkAtom(
  id: string,
  inScope: AtomRef[],
  op: OpSpec | undefined,
  outScope: AtomRef[],
  extras: Partial<Omit<Atom, 'id' | 'inScope' | 'op' | 'outScope'>> = {},
): Atom {
  return {
    id,
    kind: extras.kind ?? 'op',
    inScope,
    op,
    outScope,
    tags: extras.tags ?? [],
    wrappers: extras.wrappers ?? [],
    ref: extras.ref,
    payload: extras.payload,
  }
}

/**
 * Pre-baked wrappers for common decorator patterns.
 */
export const wrappers = {
  /** Logs input + output to ctx.trace. */
  logging(id = 'log'): AtomWrapper {
    return {
      id,
      wraps: '*',
      fn: async (ctx, next) => {
        ctx.trace('before', { inputs: ctx.inputs, atomKind: ctx.atom.kind })
        const out = await next()
        ctx.trace('after', { output: out })
        return out
      },
    }
  },

  /** Measures wrapped-section duration separately from full atom duration. */
  timing(id = 'timing'): AtomWrapper {
    return {
      id,
      wraps: '*',
      fn: async (ctx, next) => {
        const t0 = performance.now()
        const out = await next()
        ctx.trace('elapsed', { ms: performance.now() - t0 })
        return out
      },
    }
  },

  /** Input-hash cache. Naive: toString hash of inputs. */
  caching(id = 'cache'): AtomWrapper {
    const store = new Map<string, unknown>()
    return {
      id,
      wraps: '*',
      fn: async (ctx, next) => {
        const key = ctx.atom.id + ':' + JSON.stringify(ctx.inputs)
        if (store.has(key)) {
          ctx.trace('cache-hit', { key })
          return store.get(key)
        }
        ctx.trace('cache-miss', { key })
        const out = await next()
        store.set(key, out)
        return out
      },
    }
  },
}
