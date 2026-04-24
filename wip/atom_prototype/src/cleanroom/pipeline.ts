// ProjectionSlot pipeline: declared -> resolving -> materialized | shadow | problem.
//
// Slot lives as a place where a projection is declared. Its `vector` describes
// HOW the value should be assembled (literal, slotRef, rule, compose). The
// pipeline walks vectors, resolves dependencies recursively, and either fills
// in `value` (materialized / shadow) or records the failure (problem).
//
// See: docs/ATOMIC_PROJECTION_SLOT_SPEC_V0_1.md

import type {
  AtomicStore,
  JsonValue,
  ProjectionSlot,
  ProjectionSlotState,
} from './store'

export type RuleResolverContext = {
  slot: ProjectionSlot
  store: AtomicStore
  pipeline: ProjectionPipeline
}

export type RuleResolver = (body: JsonValue, ctx: RuleResolverContext) => JsonValue

export type VectorKind = 'literal' | 'slotRef' | 'rule' | 'compose'

export type ResolveOptions = {
  /** Mark final state as 'shadow' instead of 'materialized'. */
  asShadow?: boolean
}

/**
 * ProjectionPipeline grants a Store the ability to walk slot vectors and
 * transition slots through their lifecycle stages. It is intentionally
 * additive: nothing in the bootstrap Store changes; resolvers and errors
 * live on the pipeline instance.
 */
export class ProjectionPipeline {
  readonly resolvers = new Map<string, RuleResolver>()
  readonly errors = new Map<string, string>()

  constructor(readonly store: AtomicStore) {}

  /** Register a resolver for a particular rule body kind. */
  registerRuleResolver(kind: string, resolver: RuleResolver): void {
    this.resolvers.set(kind, resolver)
  }

  /**
   * Walk slot's vector and either materialize or mark as problem.
   * Idempotent for slots already in materialized/shadow.
   * Cycle-detecting: a slot already in `resolving` triggers a problem mark.
   */
  resolveSlot(slotId: string, opts: ResolveOptions = {}): ProjectionSlot {
    const slot = this.store.slots.get(slotId)
    if (!slot) throw new Error(`slot ${slotId} not found`)

    if (slot.state === 'materialized' || slot.state === 'shadow') {
      return slot
    }
    if (slot.state === 'resolving') {
      // cycle reached this slot mid-resolve
      this.errors.set(slotId, `slot ${slotId} already resolving (cycle?)`)
      return this.store.markSlot(slotId, 'problem')
    }

    this.store.markSlot(slotId, 'resolving')

    try {
      const value = this.resolveVector(slot.vector, slot)
      const finalState: ProjectionSlotState = opts.asShadow ? 'shadow' : 'materialized'
      const next: ProjectionSlot = {
        ...slot,
        value,
        state: finalState,
      }
      this.store.slots.set(slotId, next)
      this.errors.delete(slotId)
      return next
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err)
      this.errors.set(slotId, msg)
      return this.store.markSlot(slotId, 'problem')
    }
  }

  /**
   * Fork an existing slot into an independent variant in `declared` state,
   * inheriting vector + ruleRefs unless overridden. Resolve the fork with
   * `{ asShadow: true }` to mark it as a shadow alternative; resolve plain
   * to treat it as another canonical slot.
   */
  forkShadow(
    sourceId: string,
    shadowId: string,
    opts: { vectorOverride?: JsonValue; ruleOverride?: string[] } = {},
  ): ProjectionSlot {
    const source = this.store.slots.get(sourceId)
    if (!source) throw new Error(`slot ${sourceId} not found`)

    const shadow: ProjectionSlot = {
      id: shadowId,
      owner: source.owner,
      vector: opts.vectorOverride ?? source.vector,
      ruleRefs:
        opts.ruleOverride ?? (source.ruleRefs ? [...source.ruleRefs] : undefined),
      state: 'declared',
    }
    this.store.slots.set(shadowId, shadow)
    return shadow
  }

  /** Read the recorded error message (if any) for a slot in `problem` state. */
  getError(slotId: string): string | undefined {
    return this.errors.get(slotId)
  }

  // --- internal vector dispatch ----------------------------------------

  private resolveVector(vector: JsonValue, slot: ProjectionSlot): JsonValue {
    if (vector === null || typeof vector !== 'object' || Array.isArray(vector)) {
      return vector
    }

    const dispatch = vector as Record<string, JsonValue>
    const kind = dispatch.kind

    if (typeof kind !== 'string') {
      return vector
    }

    switch (kind) {
      case 'literal':
        return dispatch.value ?? null
      case 'slotRef':
        return this.resolveSlotRef(String(dispatch.slotId ?? ''))
      case 'rule':
        return this.resolveRule(String(dispatch.ruleKind ?? ''), slot)
      case 'compose': {
        const inputs = Array.isArray(dispatch.inputs) ? dispatch.inputs : []
        return inputs.map((input) => this.resolveVector(input, slot))
      }
      default:
        return vector
    }
  }

  private resolveSlotRef(refId: string): JsonValue {
    if (!refId) throw new Error('slotRef: missing slotId')
    const target = this.store.slots.get(refId)
    if (!target) throw new Error(`slotRef: slot ${refId} not found`)

    if (target.state === 'materialized' || target.state === 'shadow') {
      return target.value ?? null
    }
    if (target.state === 'declared' || target.state === 'problem') {
      const resolved = this.resolveSlot(refId)
      if (resolved.state !== 'materialized' && resolved.state !== 'shadow') {
        throw new Error(
          `slotRef: ${refId} did not materialize (state=${resolved.state})`,
        )
      }
      return resolved.value ?? null
    }
    // resolving — cycle
    throw new Error(`slotRef: ${refId} already resolving (cycle?)`)
  }

  private resolveRule(ruleKind: string, slot: ProjectionSlot): JsonValue {
    if (!ruleKind) throw new Error('rule: missing ruleKind')
    const resolver = this.resolvers.get(ruleKind)
    if (!resolver) throw new Error(`rule: no resolver registered for kind '${ruleKind}'`)

    const attached = this.store.getAttachedRules(slot.owner)
    const matching = attached.find((r) => {
      const body = r.body as Record<string, unknown> | null
      return body !== null && typeof body === 'object' && body.kind === ruleKind
    })
    if (!matching) {
      throw new Error(
        `rule: no attached rule of kind '${ruleKind}' on owner '${slot.owner}'`,
      )
    }

    return resolver(matching.body, { slot, store: this.store, pipeline: this })
  }
}
