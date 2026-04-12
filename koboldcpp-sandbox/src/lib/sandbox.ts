/**
 * Sandbox runtime — exec-first invariant.
 *
 * Invariants:
 * 1. One sandbox, one exec singleton
 * 2. All state-changing actions = exec entries (append-only JSONL messages)
 * 3. Server responses = immutable (stored as-is, never mutated)
 * 4. FS = sandbox middleware (virtual FS over runtime objects in memory)
 * 5. Node = {name, type?, meta, data}, serialized as {type}_{id}
 * 6. Source of truth: execLog (client) + serverState (immutable)
 * 7. Projection = resolve(state) → view, zero writes, one pass
 */

// ── Types ──

export interface ExecEntry {
  /** Unique id for this entry */
  id: string
  /** Operation name */
  op: string
  /** Timestamp (epoch ms) */
  ts: number
  /** Who issued */
  user: string
  /** Operation arguments */
  args: Record<string, unknown>
  /** Server response (immutable, stored as-is) */
  result?: unknown
  /** True = no server call, pure client */
  local?: boolean
}

export interface SandboxNode {
  name: string
  path: string
  type?: string
  meta: Record<string, unknown>
  data: Record<string, unknown>
  children: string[]   // child paths (refs, not objects)
  exec: string[]       // exec entry ids relevant to this node
}

/** Server node shape from /api/pchat/view */
export interface ServerNode {
  name: string
  path: string
  meta: Record<string, unknown>
  data: Record<string, unknown>
}

export interface ExecResult {
  ok: boolean
  error?: string
  data?: unknown
}

/** Materialized container result (immutable server response) */
export interface ContainerResult {
  id: string
  resolved: Record<string, unknown>
  rows: unknown[]
  ts: number
}

/** Field cell — atomic {path ↔ value} from table projection */
export interface FieldCell {
  path: string
  localName: string
  value: unknown
  valueType: string
  bind?: string
  rowKey?: string
  ref?: string
  containerId: string
}

/** Simplified table row */
export interface TableRow {
  key: string
  ref: string
  cells: Record<string, unknown>
}

/** Raw table row from server (for internal parsing) */
interface RawTableRow {
  row_key: string
  ref: string
  cells?: RawCell[]
}

interface RawCell {
  local_name: string
  value: unknown
  value_type?: string
  path?: string
  bind?: string
  atomic_path?: string
}

// ── Op handler type ──

export type OpHandler = (sb: Sandbox, entry: ExecEntry) => ExecResult

// ── Sandbox ──

let _idCounter = 0
function nextId(): string {
  return `e_${Date.now()}_${++_idCounter}`
}

export class Sandbox {
  /** Append-only exec log — source of truth for client actions */
  execLog: ExecEntry[] = []

  /** Last server response — immutable snapshot */
  serverState: ServerNode[] = []

  /** Runtime tree — derived projection, rebuilt on changes */
  tree: Map<string, SandboxNode> = new Map()

  /** Pluggable op handlers */
  private ops: Map<string, OpHandler> = new Map()

  /** Subscribers for reactive updates */
  private listeners = new Set<() => void>()

  constructor() {
    // Register built-in ops
    this.registerOp('mk', opMk)
    this.registerOp('rm', opRm)
    this.registerOp('patch', opPatch)
    this.registerOp('cd', opCd)
    this.registerOp('_server_sync', opServerSync)
  }

  // ── Op registration ──

  registerOp(name: string, handler: OpHandler) {
    this.ops.set(name, handler)
  }

  // ── Exec: all mutations go through here ──

  exec(op: string, args: Record<string, unknown> = {}, user = 'anon'): ExecResult {
    const entry: ExecEntry = {
      id: nextId(),
      op,
      ts: Date.now(),
      user,
      args,
      local: !this.ops.has(op), // unknown ops assumed server-side
    }

    // Always append to log first (source of truth)
    this.execLog.push(entry)

    const handler = this.ops.get(op)
    if (!handler) {
      entry.result = { ok: false, error: `unknown op: ${op}` }
      this.notify()
      return { ok: false, error: `unknown op: ${op}` }
    }

    const result = handler(this, entry)
    this.notify()
    return result
  }

  // ── Server exec: cmd string → server endpoint → result into log ──

  async serverExec(cmd: string, user = 'anon'): Promise<ExecResult> {
    const entry: ExecEntry = {
      id: nextId(),
      op: '_server_cmd',
      ts: Date.now(),
      user,
      args: { cmd },
      local: false,
    }
    this.execLog.push(entry)
    this.notify()

    try {
      const res = await fetch('/api/pchat/exec', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ cmd, user, log: true, scope: 'CMD' }),
      })
      const data = await res.json()
      // Store server response immutably
      entry.result = data
      this.notify()
      return { ok: true, data }
    } catch (e) {
      const error = e instanceof Error ? e.message : String(e)
      entry.result = { ok: false, error }
      this.notify()
      return { ok: false, error }
    }
  }

  // ── Load server state (immutable snapshot) ──

  async loadServerState(channel?: string, user = 'anon'): Promise<ExecResult> {
    try {
      const body: Record<string, unknown> = { user, msg_limit: 100 }
      if (channel) body.channel = channel
      const res = await fetch('/api/pchat/view', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      const data = await res.json()

      // Store as immutable server state
      const nodes: ServerNode[] = []

      // Root pchat node
      nodes.push({ name: 'pchat', path: 'pchat', meta: { type: 'pchat' }, data: {} })

      // Channels container
      if (data.channels?.length) {
        nodes.push({ name: 'channels', path: 'pchat/channels', meta: { type: 'channels' }, data: {} })
        for (const ch of data.channels) {
          const chName = ch.meta?.name ?? ch.name
          nodes.push({
            name: chName,
            path: `pchat/channels/${chName}`,
            meta: ch.meta ?? { type: 'channel', name: chName },
            data: ch.data ?? {},
          })
        }
      }

      // Messages for active channel
      if (data.active_channel && data.messages?.length) {
        for (const msg of data.messages) {
          nodes.push({
            name: msg.name,
            path: `pchat/channels/${data.active_channel}/${msg.name}`,
            meta: msg.meta ?? {},
            data: msg.data ?? {},
          })
        }
      }

      this.serverState = nodes
      this.rebuildTree()

      // Record as exec entry
      const entry: ExecEntry = {
        id: nextId(),
        op: '_load_state',
        ts: Date.now(),
        user: '_system',
        args: { channel },
        result: { ok: true, node_count: nodes.length, active_channel: data.active_channel },
        local: true,
      }
      this.execLog.push(entry)
      this.notify()

      return { ok: true, data: { node_count: nodes.length, active_channel: data.active_channel } }
    } catch (e) {
      const error = e instanceof Error ? e.message : String(e)
      return { ok: false, error }
    }
  }

  // ── Tree projection: rebuild from serverState + local ops ──

  rebuildTree() {
    const tree = new Map<string, SandboxNode>()

    // Pass 1: server nodes → runtime nodes
    for (const sn of this.serverState) {
      tree.set(sn.path, {
        name: sn.name,
        path: sn.path,
        type: sn.meta?.type as string | undefined,
        meta: { ...sn.meta },
        data: { ...sn.data },
        children: [],
        exec: [],
      })
    }

    // Pass 1b: local nodes from exec log (mk ops)
    for (const entry of this.execLog) {
      if (entry.op === 'mk') {
        const parent = (entry.args.parent as string) || ''
        const name = entry.args.name as string
        const path = parent ? `${parent}/${name}` : name
        if (!tree.has(path)) {
          tree.set(path, {
            name,
            path,
            type: entry.args.type as string | undefined,
            meta: { type: entry.args.type, user: entry.user, ts: new Date(entry.ts).toISOString() },
            data: (entry.args.data as Record<string, unknown>) ?? {},
            children: [],
            exec: [entry.id],
          })
        }
      }
    }

    // Pass 2: build children refs from path hierarchy
    for (const [path, node] of tree) {
      const lastSlash = path.lastIndexOf('/')
      if (lastSlash > 0) {
        const parentPath = path.substring(0, lastSlash)
        const parent = tree.get(parentPath)
        if (parent && !parent.children.includes(path)) {
          parent.children.push(path)
        }
      }
    }

    // Pass 3: apply local patches from exec log
    for (const entry of this.execLog) {
      if (entry.op === 'patch') {
        const nodePath = entry.args.path as string
        const node = tree.get(nodePath)
        if (node) {
          const field = entry.args.field as string
          const value = entry.args.value
          setByDotPath(node.data, field, value)
          if (!node.exec.includes(entry.id)) node.exec.push(entry.id)
        }
      }
      if (entry.op === 'rm') {
        const nodePath = entry.args.path as string
        const node = tree.get(nodePath)
        if (node) {
          node.data._deleted = true
          if (!node.exec.includes(entry.id)) node.exec.push(entry.id)
        }
      }
    }

    // Pass 4: sort children naturally (msg_1 before msg_10)
    for (const node of tree.values()) {
      node.children.sort(naturalSort)
    }

    this.tree = tree
  }

  // ── Query helpers ──

  resolve(path: string): SandboxNode | undefined {
    if (!path || path === '.') {
      // Return first root node
      for (const node of this.tree.values()) {
        if (!node.path.includes('/')) return node
      }
      return undefined
    }
    return this.tree.get(path)
  }

  /** Get root-level nodes (no slash in path) */
  roots(): SandboxNode[] {
    const result: SandboxNode[] = []
    for (const node of this.tree.values()) {
      if (!node.path.includes('/')) {
        result.push(node)
      }
    }
    return result
  }

  /** Get children of a node */
  children(path: string): SandboxNode[] {
    const node = this.tree.get(path)
    if (!node) return []
    return node.children.map(p => this.tree.get(p)).filter(Boolean) as SandboxNode[]
  }

  /** Query by path pattern (simple glob: * matches one level) */
  query(pattern: string): SandboxNode[] {
    const regex = new RegExp(
      '^' + pattern.replace(/\*/g, '[^/]+') + '$'
    )
    const result: SandboxNode[] = []
    for (const [path, node] of this.tree) {
      if (regex.test(path)) result.push(node)
    }
    return result
  }

  /** Get all nodes as flat list */
  allNodes(): SandboxNode[] {
    return Array.from(this.tree.values())
  }

  /** Get ExecEntry by id */
  getEntry(id: string): ExecEntry | undefined {
    return this.execLog.find(e => e.id === id)
  }

  // ── Container materialization (server-side projections) ──

  /** Materialized containers cache: containerId → resolved result */
  containers: Map<string, ContainerResult> = new Map()

  /** Field store: flat {path → FieldCell} from all materialized containers */
  fieldStore: Map<string, FieldCell> = new Map()

  /** Materialize a server container, store result immutably */
  async materialize(containerId: string): Promise<ExecResult> {
    const entry: ExecEntry = {
      id: nextId(),
      op: '_materialize',
      ts: Date.now(),
      user: '_system',
      args: { container_id: containerId },
      local: false,
    }
    this.execLog.push(entry)

    try {
      const res = await fetch('/api/container/materialize', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ container_id: containerId }),
      })
      const data = await res.json()
      entry.result = data

      // Store container result immutably
      const container: ContainerResult = {
        id: containerId,
        resolved: data.resolved ?? {},
        rows: data.rows ?? [],
        ts: Date.now(),
      }
      this.containers.set(containerId, container)

      // Extract fields from table projection if present
      const table = data.resolved?.table
      if (table?.rows) {
        for (const row of table.rows) {
          for (const cell of row.cells ?? []) {
            const fieldPath = cell.bind ?? cell.atomic_path ?? cell.path
            this.fieldStore.set(fieldPath, {
              path: fieldPath,
              localName: cell.local_name,
              value: cell.value,
              valueType: cell.value_type ?? typeof cell.value,
              bind: cell.bind,
              rowKey: row.row_key,
              ref: row.ref,
              containerId,
            })
          }
        }
      }

      this.notify()
      return { ok: true, data: container }
    } catch (e) {
      const error = e instanceof Error ? e.message : String(e)
      entry.result = { ok: false, error }
      this.notify()
      return { ok: false, error }
    }
  }

  /** Materialize multiple containers in parallel */
  async materializeAll(...containerIds: string[]): Promise<ExecResult> {
    const results = await Promise.all(containerIds.map(id => this.materialize(id)))
    const errors = results.filter(r => !r.ok)
    if (errors.length > 0) {
      return { ok: false, error: errors.map(e => e.error).join('; ') }
    }
    return { ok: true, data: { materialized: containerIds } }
  }

  /** Get field by canonical path */
  getField(path: string): FieldCell | undefined {
    return this.fieldStore.get(path)
  }

  /** Query fields by pattern */
  queryFields(pattern: string): FieldCell[] {
    const regex = new RegExp('^' + pattern.replace(/\*/g, '[^.]+') + '$')
    const result: FieldCell[] = []
    for (const [path, cell] of this.fieldStore) {
      if (regex.test(path)) result.push(cell)
    }
    return result
  }

  /** Get rows from a materialized container table */
  getTableRows(containerId: string): TableRow[] {
    const container = this.containers.get(containerId)
    if (!container?.resolved?.table?.rows) return []
    return container.resolved.table.rows.map((row: RawTableRow) => {
      const cells = Object.fromEntries(
        (row.cells ?? []).map((c: RawCell) => [c.local_name, c.value])
      )
      return { key: row.row_key, ref: row.ref, cells }
    })
  }

  // ── Subscribe ──

  subscribe(fn: () => void): () => void {
    this.listeners.add(fn)
    return () => this.listeners.delete(fn)
  }

  private notify() {
    this.listeners.forEach(fn => fn())
  }

  // ── Serialization ──

  /** Exec log as JSONL string (for debug/export) */
  toJSONL(): string {
    return this.execLog.map(e => JSON.stringify(e)).join('\n')
  }

  /** Tree as JSON (for debug) */
  toJSON(): Record<string, unknown> {
    const obj: Record<string, unknown> = {}
    for (const [path, node] of this.tree) {
      obj[path] = {
        name: node.name,
        type: node.type,
        meta: node.meta,
        data: node.data,
        children_count: node.children.length,
        exec_count: node.exec.length,
      }
    }
    return obj
  }
}

// ── Built-in op handlers ──

const opMk: OpHandler = (sb, entry) => {
  const parent = (entry.args.parent as string) || ''
  const name = entry.args.name as string
  if (!name) return { ok: false, error: 'mk: name required' }

  const path = parent ? `${parent}/${name}` : name
  if (sb.tree.has(path)) return { ok: true, data: { path, exists: true } }

  const node: SandboxNode = {
    name,
    path,
    type: entry.args.type as string | undefined,
    meta: { type: entry.args.type, user: entry.user, ts: new Date(entry.ts).toISOString() },
    data: (entry.args.data as Record<string, unknown>) ?? {},
    children: [],
    exec: [entry.id],
  }
  sb.tree.set(path, node)

  // Add to parent's children
  if (parent) {
    const parentNode = sb.tree.get(parent)
    if (parentNode && !parentNode.children.includes(path)) {
      parentNode.children.push(path)
    }
  }

  return { ok: true, data: { path } }
}

const opRm: OpHandler = (sb, entry) => {
  const path = entry.args.path as string
  if (!path) return { ok: false, error: 'rm: path required' }
  const node = sb.tree.get(path)
  if (!node) return { ok: false, error: `rm: not found: ${path}` }
  node.data._deleted = true
  node.exec.push(entry.id)
  return { ok: true }
}

const opPatch: OpHandler = (sb, entry) => {
  const path = entry.args.path as string
  const field = entry.args.field as string
  const value = entry.args.value
  if (!path || !field) return { ok: false, error: 'patch: path and field required' }
  const node = sb.tree.get(path)
  if (!node) return { ok: false, error: `patch: not found: ${path}` }
  setByDotPath(node.data, field, value)
  node.exec.push(entry.id)
  return { ok: true }
}

const opCd: OpHandler = (_sb, entry) => {
  // Navigation is just a recorded intent, no tree mutation
  entry.local = true
  return { ok: true, data: { path: entry.args.path } }
}

const opServerSync: OpHandler = (_sb, entry) => {
  // Server sync is a passthrough — result already stored in entry
  entry.local = true
  return { ok: true, data: entry.args.result }
}

// ── Utilities ──

function setByDotPath(obj: Record<string, unknown>, path: string, value: unknown) {
  const parts = path.split('.')
  let cur = obj
  for (let i = 0; i < parts.length - 1; i++) {
    if (!(parts[i] in cur) || typeof cur[parts[i]] !== 'object') {
      cur[parts[i]] = {}
    }
    cur = cur[parts[i]] as Record<string, unknown>
  }
  cur[parts[parts.length - 1]] = value
}

function naturalSort(a: string, b: string): number {
  return a.localeCompare(b, undefined, { numeric: true })
}
