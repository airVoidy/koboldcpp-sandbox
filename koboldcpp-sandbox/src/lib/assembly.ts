/**
 * Client-side Assembly DSL interpreter.
 *
 * Mirrors Python assembly_dsl.py:
 *   - Same Instruction dataclass (opcode, args, flags, line, raw)
 *   - Same 10 opcodes: MOV, GEN, PUT, PUT+, PARSE, CALL, CMP, JIF, LOOP, EACH
 *   - Same ref resolution: @ → state, $ → config/vars, quoted → literal
 *   - Same label resolution: :label → +N offset
 *
 * Client executes: MOV, PUT, PUT+, CMP, JIF, LOOP, EACH, NOP, LABEL
 * Server required: GEN, CALL, PARSE (needs LLM / server transforms)
 */

// ── Dataclasses (mirrors Python @dataclass) ──

export interface Instruction {
  opcode: string        // MOV, GEN, PUT, PUT+, PARSE, CALL, CMP, JIF, LOOP, EACH, NOP
  args: string[]        // raw string tokens
  flags: Record<string, string>  // key:value pairs
  line: number          // source line number
  raw: string           // original text
}

export interface AsmFunction {
  name: string
  params: string[]      // ["@chat", "$prompt", ...]
  outputs: string[]     // ["@draft", "@constraints", ...]
  instructions: Instruction[]
}

export interface AsmResult {
  state: Record<string, unknown>
  log: Array<Record<string, unknown>>
  error: string | null
}

// ── State (mirrors WorkflowContext subset) ──

export interface AsmState {
  /** @ refs — mutable state */
  state: Record<string, unknown>
  /** $ refs — config/vars (read-only during run) */
  vars: Record<string, unknown>
  /** Execution log */
  log: Array<{ op: string; args: string[]; result?: unknown }>
  /** Program counter */
  pc: number
  /** Halted flag */
  halted: boolean
  /** Pending server calls */
  serverCalls: Array<{ instruction: Instruction; index: number }>
}

export function createState(
  initial?: Record<string, unknown>,
  vars?: Record<string, unknown>,
): AsmState {
  return {
    state: { ...initial },
    vars: { ...vars },
    log: [],
    pc: 0,
    halted: false,
    serverCalls: [],
  }
}

// ── Tokeniser (mirrors _tokenise_line) ──

const FLAG_RE = /^([A-Za-z_]\w*):(.+)$/

function splitAsmArgs(text: string): string[] {
  const args: string[] = []
  let current = ''
  let depth = 0
  let quote: string | null = null
  let escaped = false

  for (const ch of text) {
    if (escaped) { current += ch; escaped = false; continue }
    if (ch === '\\' && quote) { current += ch; escaped = true; continue }
    if (quote) { current += ch; if (ch === quote) quote = null; continue }
    if (ch === '"' || ch === "'") { quote = ch; current += ch; continue }
    if ('([{'.includes(ch)) { depth++; current += ch; continue }
    if (')]}'.includes(ch)) { depth = Math.max(0, depth - 1); current += ch; continue }
    if (ch === ',' && depth === 0) {
      if (current.trim()) args.push(current.trim())
      current = ''
      continue
    }
    current += ch
  }
  if (current.trim()) args.push(current.trim())
  return args
}

function tokeniseLine(raw: string): Instruction | null {
  let line = raw.trim()

  // Strip comments (respecting quotes)
  let inQuote = false
  let qChar = ''
  for (let i = 0; i < line.length; i++) {
    const ch = line[i]
    if ((ch === '"' || ch === "'") && !inQuote) { inQuote = true; qChar = ch }
    else if (ch === qChar && inQuote) { inQuote = false }
    else if (ch === ';' && !inQuote) { line = line.slice(0, i).trimEnd(); break }
  }

  if (!line) return null

  const parts = line.split(/\s+/, 2)
  const opcode = parts[0].toUpperCase()
  const rest = parts.length > 1 ? line.slice(parts[0].length).trim() : ''

  const tokens = splitAsmArgs(rest)
  const args: string[] = []
  const flags: Record<string, string> = {}
  for (const tok of tokens) {
    const m = FLAG_RE.exec(tok)
    if (m) { flags[m[1]] = m[2] }
    else { args.push(tok) }
  }

  return { opcode, args, flags, line: 0, raw }
}

// ── Parser (mirrors parse_program) ──

export function parseProgram(text: string): { instructions: Instruction[]; functions: Record<string, AsmFunction> } {
  const lines = text.split('\n')
  const instructions: Instruction[] = []
  const functions: Record<string, AsmFunction> = {}

  let i = 0
  while (i < lines.length) {
    const stripped = lines[i].trim()
    if (!stripped || stripped.startsWith(';') || stripped.startsWith('#')) { i++; continue }

    // Label :name
    if (stripped.startsWith(':') && !stripped.startsWith('::')) {
      const labelName = stripped.slice(1).trim()
      instructions.push({ opcode: 'LABEL', args: [labelName], flags: {}, line: i + 1, raw: stripped })
      i++; continue
    }

    // fn declaration
    if (stripped.startsWith('fn ')) {
      const { fn, consumed } = parseFnBlock(lines, i)
      fn.instructions = resolveLabels(fn.instructions)
      functions[fn.name] = fn
      i += consumed; continue
    }

    const inst = tokeniseLine(stripped)
    if (inst) { inst.line = i + 1; instructions.push(inst) }
    i++
  }

  return { instructions: resolveLabels(instructions), functions }
}

function parseFnBlock(lines: string[], start: number): { fn: AsmFunction; consumed: number } {
  const header = lines[start].trim()
  const m = header.match(/^fn\s+(\w+)\(([^)]*)\)(?:\s*->\s*([^:]+))?\s*:/)
  if (!m) throw new Error(`Bad fn declaration at line ${start + 1}: ${header}`)

  const name = m[1]
  const params = m[2] ? m[2].split(',').map(s => s.trim()).filter(Boolean) : []
  const outputs = m[3] ? m[3].split(',').map(s => s.trim()).filter(Boolean) : []

  const fnInstrs: Instruction[] = []
  let consumed = 1
  let i = start + 1
  while (i < lines.length) {
    const raw = lines[i]
    if (raw && raw[0] !== ' ' && raw[0] !== '\t') break
    const stripped = raw.trim()
    if (stripped && !stripped.startsWith(';') && !stripped.startsWith('#')) {
      if (stripped.startsWith(':') && !stripped.startsWith('::')) {
        fnInstrs.push({ opcode: 'LABEL', args: [stripped.slice(1).trim()], flags: {}, line: i + 1, raw: stripped })
      } else {
        const inst = tokeniseLine(stripped)
        if (inst) { inst.line = i + 1; fnInstrs.push(inst) }
      }
    }
    consumed++; i++
  }

  return { fn: { name, params, outputs, instructions: resolveLabels(fnInstrs) }, consumed }
}

function resolveLabels(instructions: Instruction[]): Instruction[] {
  const labels: Record<string, number> = {}
  const real: Instruction[] = []
  for (const inst of instructions) {
    if (inst.opcode === 'LABEL') { labels[inst.args[0] ?? ''] = real.length }
    else { real.push(inst) }
  }
  for (let ip = 0; ip < real.length; ip++) {
    if (['JIF', 'LOOP', 'EACH'].includes(real[ip].opcode)) {
      real[ip].args = real[ip].args.map(arg => {
        if (arg.startsWith(':')) {
          const target = labels[arg.slice(1)]
          if (target !== undefined) {
            const offset = target - ip - 1
            return offset < 0 ? `${offset}` : `+${offset}`
          }
        }
        return arg
      })
    }
  }
  return real
}

// ── Ref resolution (mirrors _asm_resolve) ──

function resolve(token: string, ctx: AsmState): unknown {
  const t = token.trim()

  // Quoted string
  if (t.length >= 2 && t[0] === t[t.length - 1] && (t[0] === '"' || t[0] === "'")) {
    return t.slice(1, -1).replace(/\\n/g, '\n').replace(/\\t/g, '\t')
  }

  // Number
  if (/^-?\d+(\.\d+)?$/.test(t)) return parseFloat(t)

  // @ ref → state
  if (t.startsWith('@')) {
    const path = t.slice(1)
    return getPath(ctx.state, path)
  }

  // $ ref → vars
  if (t.startsWith('$')) {
    const path = t.slice(1)
    return getPath(ctx.vars, path)
  }

  // Bare word → string
  return t
}

function getPath(obj: unknown, path: string): unknown {
  let cur = obj
  for (const part of path.split('.')) {
    if (cur == null || typeof cur !== 'object') return undefined
    cur = (cur as Record<string, unknown>)[part]
  }
  return cur
}

function setPath(obj: Record<string, unknown>, path: string, value: unknown) {
  const parts = path.split('.')
  let cur = obj
  for (let i = 0; i < parts.length - 1; i++) {
    if (!(parts[i] in cur) || typeof cur[parts[i]] !== 'object') cur[parts[i]] = {}
    cur = cur[parts[i]] as Record<string, unknown>
  }
  cur[parts[parts.length - 1]] = value
}

// ── Client-side opcode handlers ──

type OpHandler = (inst: Instruction, ctx: AsmState) => void

const CLIENT_OPS: Record<string, OpHandler> = {
  // MOV @dst, src — copy resolved value into state
  MOV(inst, ctx) {
    if (inst.args.length >= 2 && inst.args[0].startsWith('@')) {
      const dst = inst.args[0].slice(1)
      const val = resolve(inst.args[1], ctx)
      setPath(ctx.state, dst, val)
    }
  },

  // PUT @dst, val — same as MOV (alias)
  PUT(inst, ctx) { CLIENT_OPS.MOV(inst, ctx) },

  // 'PUT+' — append to array
  'PUT+'(inst, ctx) {
    if (inst.args.length >= 2 && inst.args[0].startsWith('@')) {
      const dst = inst.args[0].slice(1)
      const existing = getPath(ctx.state, dst)
      const val = resolve(inst.args[1], ctx)
      const arr = Array.isArray(existing) ? [...existing, val] : [val]
      setPath(ctx.state, dst, arr)
    }
  },

  // CMP @dst, a, b — compare → @dst = 0 (eq) / -1 (lt) / 1 (gt)
  CMP(inst, ctx) {
    if (inst.args.length >= 3 && inst.args[0].startsWith('@')) {
      const a = resolve(inst.args[1], ctx)
      const b = resolve(inst.args[2], ctx)
      const r = a === b ? 0 : (a as number) < (b as number) ? -1 : 1
      setPath(ctx.state, inst.args[0].slice(1), r)
    }
  },

  // JIF cond, +offset — jump if truthy
  JIF(inst, ctx) {
    if (inst.args.length >= 2) {
      const cond = resolve(inst.args[0], ctx)
      if (cond) {
        const offset = parseInt(inst.args[1], 10)
        if (!isNaN(offset)) ctx.pc += offset // relative jump
      }
    }
  },

  // EACH @item, @list, +bodyLen — iterate
  EACH(inst, ctx) {
    // Client-side EACH: simplified, doesn't handle body offset properly
    // Full EACH with body needs server or extended client interpreter
    if (inst.args.length >= 2) {
      const list = resolve(inst.args[1], ctx)
      if (Array.isArray(list) && inst.args[0].startsWith('@')) {
        // Store list for iteration — consumer reads @item per iteration
        setPath(ctx.state, inst.args[0].slice(1), list)
      }
    }
  },

  // LOOP — no-op on client (server manages iteration)
  LOOP() {},

  // NOP
  NOP() {},
}

/** Server-required opcodes */
const SERVER_OPS = new Set(['GEN', 'CALL', 'PARSE'])

// ── Executor ──

/**
 * Run assembly instructions. Client ops execute immediately.
 * Server ops (GEN, CALL, PARSE) are collected in ctx.serverCalls.
 */
export function run(
  instructions: Instruction[],
  initial?: Record<string, unknown>,
  vars?: Record<string, unknown>,
): AsmState {
  const ctx = createState(initial, vars)

  while (ctx.pc < instructions.length && !ctx.halted) {
    const inst = instructions[ctx.pc]

    if (SERVER_OPS.has(inst.opcode)) {
      ctx.serverCalls.push({ instruction: inst, index: ctx.pc })
      ctx.log.push({ op: inst.opcode, args: inst.args, result: '→server' })
      ctx.pc++
      continue
    }

    const handler = CLIENT_OPS[inst.opcode]
    if (handler) {
      handler(inst, ctx)
      ctx.log.push({ op: inst.opcode, args: inst.args })
    } else {
      // Unknown → server
      ctx.serverCalls.push({ instruction: inst, index: ctx.pc })
      ctx.log.push({ op: inst.opcode, args: inst.args, result: '→server' })
    }
    ctx.pc++
  }

  return ctx
}

/** Check if program is fully client-executable */
export function isClientOnly(instructions: Instruction[]): boolean {
  return instructions.every(i => !SERVER_OPS.has(i.opcode))
}

/** Convert AsmState to AsmResult (mirrors Python) */
export function toResult(ctx: AsmState): AsmResult {
  return {
    state: ctx.state,
    log: ctx.log,
    error: null,
  }
}
