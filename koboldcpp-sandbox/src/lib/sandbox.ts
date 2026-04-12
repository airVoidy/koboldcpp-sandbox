/**
 * Sandbox runtime: single FS node tree + single exec queue.
 *
 * Invariants:
 * - One sandbox, one exec singleton
 * - All state-changing actions = exec entries (immutable, push-only)
 * - L0 = linear exec pipeline. No cycles, no recursion.
 * - Node = {name, type?, children, meta, data}. Name unique per scope.
 * - Runtime objects live in memory. FS serialization = lazy/debug.
 * - Types are generic (card = {}, cards = [])
 */

// ── Node: atomic runtime object ──

export interface SandboxNode {
  name: string
  type?: string
  meta: Record<string, unknown>
  data: Record<string, unknown>
  children: Map<string, SandboxNode>
  exec: ExecEntry[]
  parent: SandboxNode | null
}

export interface ExecEntry {
  op: string
  ts: number
  user: string
  args: Record<string, unknown>
}

// ── Sandbox: single root + exec queue ──

export class Sandbox {
  root: SandboxNode
  execLog: ExecEntry[] = []
  private listeners = new Set<() => void>()

  constructor() {
    this.root = createNode('root', null, { type: 'root' })
  }

  /** Subscribe to state changes */
  subscribe(fn: () => void) {
    this.listeners.add(fn)
    return () => this.listeners.delete(fn)
  }

  private notify() {
    this.listeners.forEach(fn => fn())
  }

  /** Execute a command — all mutations go through here */
  exec(op: string, args: Record<string, unknown>, user = 'anon'): ExecResult {
    const entry: ExecEntry = { op, ts: Date.now(), user, args }
    this.execLog.push(entry)

    const handler = EXEC_OPS[op]
    if (!handler) {
      return { ok: false, error: `unknown op: ${op}` }
    }

    const result = handler(this, entry)
    this.notify()
    return result
  }

  /** Resolve node by path (dot-separated or slash-separated) */
  resolve(path: string): SandboxNode | null {
    if (!path || path === '.' || path === 'root') return this.root
    const parts = path.replace(/\\/g, '/').split(/[./]/).filter(Boolean)
    let cur = this.root
    for (const part of parts) {
      const child = cur.children.get(part)
      if (!child) return null
      cur = child
    }
    return cur
  }

  /** Get flat list of all nodes (for table view) */
  flatten(node?: SandboxNode, prefix = ''): Array<{ path: string; node: SandboxNode }> {
    const n = node ?? this.root
    const path = prefix ? `${prefix}/${n.name}` : n.name
    const result: Array<{ path: string; node: SandboxNode }> = [{ path, node: n }]
    for (const child of n.children.values()) {
      result.push(...this.flatten(child, path))
    }
    return result
  }

  /** Serialize to JSON (for debug/transport) */
  toJSON(): unknown {
    return serializeNode(this.root)
  }
}

// ── Exec result ──

export interface ExecResult {
  ok: boolean
  error?: string
  node?: SandboxNode
  data?: unknown
}

// ── Node factory ──

export function createNode(
  name: string,
  parent: SandboxNode | null,
  meta: Record<string, unknown> = {},
  data: Record<string, unknown> = {},
): SandboxNode {
  return { name, type: meta.type as string | undefined, meta, data, children: new Map(), exec: [], parent }
}

// ── Exec operations: all state changes ──

type ExecHandler = (sb: Sandbox, entry: ExecEntry) => ExecResult

const EXEC_OPS: Record<string, ExecHandler> = {
  /** Create a child node */
  mk(sb, entry) {
    const { parent: parentPath, name, type, data } = entry.args as {
      parent?: string; name: string; type?: string; data?: Record<string, unknown>
    }
    const parent = parentPath ? sb.resolve(parentPath as string) : sb.root
    if (!parent) return { ok: false, error: `parent not found: ${parentPath}` }
    if (parent.children.has(name)) return { ok: true, node: parent.children.get(name)! }

    const meta: Record<string, unknown> = { type: type ?? 'card', user: entry.user, ts: new Date(entry.ts).toISOString() }
    if (type) meta.name = name
    const node = createNode(name, parent, meta, data ?? {})
    parent.children.set(name, node)
    node.exec.push(entry)
    return { ok: true, node }
  },

  /** Post a message (auto-numbered) */
  post(sb, entry) {
    const { parent: parentPath, content } = entry.args as { parent?: string; content: string }
    const parent = parentPath ? sb.resolve(parentPath as string) : sb.root
    if (!parent) return { ok: false, error: `parent not found: ${parentPath}` }

    // Find next msg_N
    let maxN = 0
    for (const key of parent.children.keys()) {
      if (key.startsWith('msg_')) {
        const n = parseInt(key.slice(4), 10)
        if (n > maxN) maxN = n
      }
    }
    const name = `msg_${maxN + 1}`
    const meta = { type: 'message', user: entry.user, ts: new Date(entry.ts).toISOString() }
    const data = { content, reactions: {} }
    const node = createNode(name, parent, meta, data)
    parent.children.set(name, node)
    node.exec.push(entry)
    return { ok: true, node }
  },

  /** Delete a child node (soft: mark _deleted) */
  rm(sb, entry) {
    const { parent: parentPath, name } = entry.args as { parent?: string; name: string }
    const parent = parentPath ? sb.resolve(parentPath as string) : sb.root
    if (!parent) return { ok: false, error: `parent not found: ${parentPath}` }
    const node = parent.children.get(name)
    if (!node) return { ok: false, error: `not found: ${name}` }
    node.data._deleted = true
    node.exec.push(entry)
    return { ok: true, node }
  },

  /** Patch a field by dot-path */
  patch(sb, entry) {
    const { path, field, value } = entry.args as { path?: string; field: string; value: unknown }
    const node = path ? sb.resolve(path as string) : sb.root
    if (!node) return { ok: false, error: `not found: ${path}` }

    // Set by dot-path in data
    const parts = field.split('.')
    let cur: Record<string, unknown> = node.data
    for (let i = 0; i < parts.length - 1; i++) {
      if (!(parts[i] in cur) || typeof cur[parts[i]] !== 'object') {
        cur[parts[i]] = {}
      }
      cur = cur[parts[i]] as Record<string, unknown>
    }
    cur[parts[parts.length - 1]] = value
    node.exec.push(entry)
    return { ok: true, node }
  },

  /** Toggle reaction */
  react(sb, entry) {
    const { path, emoji } = entry.args as { path: string; emoji: string }
    const node = sb.resolve(path)
    if (!node) return { ok: false, error: `not found: ${path}` }

    const reactions = (node.data.reactions ?? {}) as Record<string, { users: string[]; count: number }>
    const existing = reactions[emoji] ?? { users: [], count: 0 }
    const users = existing.users.includes(entry.user)
      ? existing.users.filter(u => u !== entry.user)
      : [...existing.users, entry.user]

    if (users.length === 0) {
      delete reactions[emoji]
    } else {
      reactions[emoji] = { users, count: users.length }
    }
    node.data.reactions = reactions
    node.exec.push(entry)
    return { ok: true, node, data: { reactions } }
  },

  /** Create channel (convenience) */
  mkchannel(sb, entry) {
    const { name } = entry.args as { name: string }
    // Ensure channels container
    if (!sb.root.children.has('channels')) {
      const channels = createNode('channels', sb.root, { type: 'channels', name: 'channels' })
      sb.root.children.set('channels', channels)
    }
    const channels = sb.root.children.get('channels')!
    if (channels.children.has(name)) {
      return { ok: true, node: channels.children.get(name)! }
    }
    const ch = createNode(name, channels, { type: 'channel', user: entry.user, ts: new Date(entry.ts).toISOString(), name })
    channels.children.set(name, ch)
    ch.exec.push(entry)
    return { ok: true, node: ch }
  },
}

// ── Serialization ──

function serializeNode(node: SandboxNode): unknown {
  const children: Record<string, unknown> = {}
  for (const [name, child] of node.children) {
    children[name] = serializeNode(child)
  }
  return {
    name: node.name,
    type: node.type,
    meta: node.meta,
    data: node.data,
    children: Object.keys(children).length > 0 ? children : undefined,
    exec_count: node.exec.length,
  }
}
