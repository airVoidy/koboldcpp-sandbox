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

export interface ExecEntry {
  id: string
  op: string
  ts: number
  user: string
  args: Record<string, unknown>
  result?: unknown
  local?: boolean
}

export interface SandboxNode {
  name: string
  path: string
  type?: string
  meta: Record<string, unknown>
  data: Record<string, unknown>
  children: string[]
  /** Virtual typed child lists derived from children[] */
  childLists: Record<string, string[]>
  exec: string[]
  /** Declared capabilities: what this node's scope allows */
  capabilities: {
    /** children[] open = can create nested nodes. string[] = allowed types, true = any */
    children?: string[] | true
    /** exec declared = can receive exec commands */
    exec?: boolean
    /** append declarations: type → allowed (e.g. {msg: true} = can post messages) */
    append?: Record<string, boolean>
  }
}

export interface TypedListEntry {
  kind: string
  index: number
  role: 'template' | 'instance'
  virtual: boolean
  path: string
  node?: SandboxNode
}

export interface TypedScopeDescriptor {
  kind: string
  hostPath: string
  scopePath: string
  templatePath: string
  instancePattern: string
  template: TypedListEntry
  items: TypedListEntry[]
}

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

export interface FieldCell {
  path: string
  localName: string
  value: unknown
  valueType: string
  bind?: string
  ref?: string
}

export interface RuntimeRow {
  rowId: string
  scopeId: string
  originExecId?: string
  kind: 'intent' | 'reply' | 'live'
  entityId: string
  entityType: string
  name: string
  value: unknown
  valueType: string
  localPath: string
  globalPath?: string
  meta: Record<string, unknown>
}

export interface ExecScopeSnapshot {
  id: string
  request?: ExecEntry
  response?: unknown
  rows: RuntimeRow[]
}

export interface SandboxSnapshot {
  version: 1
  execLog: ExecEntry[]
  serverState: ServerNode[]
}

export interface SandboxDiff {
  execAdded: string[]
  execRemoved: string[]
  nodesAdded: string[]
  nodesRemoved: string[]
  fieldsAdded: string[]
  fieldsRemoved: string[]
  rowsAdded: string[]
  rowsRemoved: string[]
}

export interface ReplayRunResult {
  result: ExecResult
  after: SandboxSnapshot
  diff: SandboxDiff
}

export type OpHandler = (sb: Sandbox, entry: ExecEntry) => ExecResult

let _idCounter = 0
function nextId(): string {
  return `e_${Date.now()}_${++_idCounter}`
}

export class Sandbox {
  execLog: ExecEntry[] = []
  serverState: ServerNode[] = []
  tree: Map<string, SandboxNode> = new Map()
  fieldStore: Map<string, FieldCell> = new Map()

  private ops: Map<string, OpHandler> = new Map()
  private listeners = new Set<() => void>()

  constructor() {
    this.registerOp('mk', opMk)
    this.registerOp('rm', opRm)
    this.registerOp('patch', opPatch)
    this.registerOp('cd', opCd)
    this.registerOp('_server_sync', opServerSync)
  }

  registerOp(name: string, handler: OpHandler) {
    this.ops.set(name, handler)
  }

  exec(op: string, args: Record<string, unknown> = {}, user = 'anon'): ExecResult {
    const entry: ExecEntry = {
      id: nextId(),
      op,
      ts: Date.now(),
      user,
      args,
      local: !this.ops.has(op),
    }

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

      const nodes: ServerNode[] = []
      nodes.push({ name: 'pchat', path: 'pchat', meta: { type: 'pchat' }, data: {} })

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
      this.rebuildFieldStore()

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

  rebuildTree() {
    const tree = new Map<string, SandboxNode>()

    // Pass 1: server nodes → runtime nodes (with capabilities from type)
    for (const sn of this.serverState) {
      const type = sn.meta?.type as string | undefined
      tree.set(sn.path, {
        name: sn.name,
        path: sn.path,
        type,
        meta: { ...sn.meta },
        data: { ...sn.data },
        children: [],
        childLists: {},
        exec: [],
        capabilities: capabilitiesFromType(type),
      })
    }

    for (const entry of this.execLog) {
      if (entry.op === 'mk') {
        const parent = (entry.args.parent as string) || ''
        const name = entry.args.name as string
        const type = entry.args.type as string | undefined
        const path = parent ? `${parent}/${name}` : name
        if (!tree.has(path)) {
          const caps = (entry.args.capabilities as SandboxNode['capabilities']) ?? {}
          tree.set(path, {
            name,
            path,
            type,
            meta: { type, user: entry.user, ts: new Date(entry.ts).toISOString() },
            data: (entry.args.data as Record<string, unknown>) ?? {},
            children: [],
            childLists: {},
            exec: [entry.id],
            capabilities: {
              exec: caps.exec ?? true,
              children: caps.children,
              append: caps.append,
            },
          })
        }
      }
    }

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

    for (const node of tree.values()) {
      node.children.sort(naturalSort)
      node.childLists = buildChildLists(tree, node, node.children)
    }

    this.tree = tree
  }

  resolve(path: string): SandboxNode | undefined {
    if (!path || path === '.') {
      for (const node of this.tree.values()) {
        if (!node.path.includes('/')) return node
      }
      return undefined
    }
    return this.tree.get(path)
  }

  roots(): SandboxNode[] {
    const result: SandboxNode[] = []
    for (const node of this.tree.values()) {
      if (!node.path.includes('/')) result.push(node)
    }
    return result
  }

  children(path: string): SandboxNode[] {
    const node = this.tree.get(path)
    if (!node) return []
    return node.children.map(p => this.tree.get(p)).filter(Boolean) as SandboxNode[]
  }

  childListKinds(path: string): string[] {
    const node = this.tree.get(path)
    if (!node) return []
    return Object.keys(node.childLists).sort(naturalSort)
  }

  childrenByKind(path: string, kind: string): SandboxNode[] {
    const node = this.tree.get(path)
    if (!node) return []
    const refs = node.childLists[kind] ?? []
    return refs.map(p => this.tree.get(p)).filter(Boolean) as SandboxNode[]
  }

  typedList(path: string, kind: string): TypedListEntry[] {
    const node = this.tree.get(path)
    if (!node) return []

    const refs = [...(node.childLists[kind] ?? [])]
    const templateRef = refs.find((ref) => this.tree.get(ref)?.name === kind)
    const instanceRefs = refs.filter((ref) => ref !== templateRef).sort(naturalSort)
    const entries: TypedListEntry[] = []

    if (templateRef) {
      entries.push({
        kind,
        index: 0,
        role: 'template',
        virtual: false,
        path: templateRef,
        node: this.tree.get(templateRef),
      })
    } else {
      const virtualTemplate = buildVirtualTemplateNode(path, kind)
      entries.push({
        kind,
        index: 0,
        role: 'template',
        virtual: true,
        path: virtualTemplate.path,
        node: virtualTemplate,
      })
    }

    instanceRefs.forEach((ref, offset) => {
      entries.push({
        kind,
        index: offset + 1,
        role: 'instance',
        virtual: false,
        path: ref,
        node: this.tree.get(ref),
      })
    })

    return entries
  }

  templateOf(path: string, kind: string): TypedListEntry | undefined {
    return this.typedList(path, kind)[0]
  }

  instancesOf(path: string, kind: string): SandboxNode[] {
    return this.typedList(path, kind)
      .filter((entry) => entry.role === 'instance')
      .map((entry) => entry.node)
      .filter(Boolean) as SandboxNode[]
  }

  typedScope(path: string, kind: string): TypedScopeDescriptor | undefined {
    const node = this.tree.get(path)
    if (!node) return undefined

    const items = this.typedList(path, kind)
    const template = items[0]
    if (!template) return undefined

    return {
      kind,
      hostPath: path,
      scopePath: `${path}.${kind}`,
      templatePath: `${path}.${kind}[0]`,
      instancePattern: `${path}.${kind}[{${kind}_$}]`,
      template,
      items,
    }
  }

  query(pattern: string): SandboxNode[] {
    const regex = new RegExp('^' + pattern.replace(/\*/g, '[^/]+') + '$')
    const result: SandboxNode[] = []
    for (const [path, node] of this.tree) {
      if (regex.test(path)) result.push(node)
    }
    return result
  }

  allNodes(): SandboxNode[] {
    return Array.from(this.tree.values())
  }

  getEntry(id: string): ExecEntry | undefined {
    return this.execLog.find(e => e.id === id)
  }

  rebuildFieldStore() {
    this.fieldStore.clear()
    for (const [, node] of this.tree) {
      for (const [key, value] of Object.entries(node.meta)) {
        const path = `${node.path}._meta.${key}`
        this.fieldStore.set(path, {
          path,
          localName: key,
          value,
          valueType: typeof value,
          ref: node.path,
        })
      }
      for (const [key, value] of Object.entries(node.data)) {
        if (key === '_deleted' && !value) continue
        const path = `${node.path}._data.${key}`
        this.fieldStore.set(path, {
          path,
          localName: key,
          value,
          valueType: typeof value,
          ref: node.path,
        })
      }
    }
  }

  getField(path: string): FieldCell | undefined {
    return this.fieldStore.get(path)
  }

  queryFields(pattern: string): FieldCell[] {
    const regex = new RegExp('^' + pattern.replace(/\*/g, '[^.]+') + '$')
    const result: FieldCell[] = []
    for (const [path, cell] of this.fieldStore) {
      if (regex.test(path)) result.push(cell)
    }
    return result
  }

  runtimeRows(): RuntimeRow[] {
    const rows: RuntimeRow[] = []

    for (const entry of this.execLog) {
      const scopeId = `exec:${entry.id}`
      const rawIntent = entry.args.cmd ?? entry.args
      rows.push({
        rowId: `${scopeId}:intent`,
        scopeId,
        originExecId: entry.id,
        kind: 'intent',
        entityId: entry.id,
        entityType: 'exec_scope',
        name: 'request',
        value: rawIntent,
        valueType: valueTypeOf(rawIntent),
        localPath: 'request',
        meta: {
          op: entry.op,
          ts: entry.ts,
          user: entry.user,
          local: !!entry.local,
        },
      })

      if (entry.result !== undefined) {
        rows.push({
          rowId: `${scopeId}:reply`,
          scopeId,
          originExecId: entry.id,
          kind: 'reply',
          entityId: entry.id,
          entityType: 'exec_scope',
          name: 'response',
          value: entry.result,
          valueType: valueTypeOf(entry.result),
          localPath: 'response',
          meta: {
            op: entry.op,
            ts: entry.ts,
            user: entry.user,
            local: !!entry.local,
          },
        })

        for (const leaf of flattenValueLeaves(entry.result, 'response')) {
          rows.push({
            rowId: `${scopeId}:${leaf.path}`,
            scopeId,
            originExecId: entry.id,
            kind: 'reply',
            entityId: entry.id,
            entityType: 'exec_scope',
            name: leaf.name,
            value: leaf.value,
            valueType: valueTypeOf(leaf.value),
            localPath: leaf.path,
            meta: {
              op: entry.op,
              ts: entry.ts,
              user: entry.user,
              local: !!entry.local,
            },
          })
        }
      }
    }

    for (const [, node] of this.tree) {
      const scopeId = `node:${node.path}`
      const entityType = node.type ?? (typeof node.meta.type === 'string' ? node.meta.type : 'node')
      rows.push({
        rowId: `${scopeId}:self`,
        scopeId,
        kind: 'live',
        entityId: node.path,
        entityType,
        name: node.name,
        value: {
          meta: node.meta,
          data: node.data,
        },
        valueType: 'object',
        localPath: '.',
        globalPath: node.path,
        meta: {
          path: node.path,
          type: entityType,
        },
      })

      for (const [key, value] of Object.entries(node.meta)) {
        rows.push({
          rowId: `${scopeId}:_meta.${key}`,
          scopeId,
          kind: 'live',
          entityId: node.path,
          entityType,
          name: key,
          value,
          valueType: valueTypeOf(value),
          localPath: `_meta.${key}`,
          globalPath: `${node.path}._meta.${key}`,
          meta: {
            scope: '_meta',
            path: node.path,
            type: entityType,
          },
        })
      }

      for (const [key, value] of Object.entries(node.data)) {
        rows.push({
          rowId: `${scopeId}:_data.${key}`,
          scopeId,
          kind: 'live',
          entityId: node.path,
          entityType,
          name: key,
          value,
          valueType: valueTypeOf(value),
          localPath: `_data.${key}`,
          globalPath: `${node.path}._data.${key}`,
          meta: {
            scope: '_data',
            path: node.path,
            type: entityType,
          },
        })
      }
    }

    return rows
  }

  execScopes(): ExecScopeSnapshot[] {
    return this.execLog.map((entry) => {
      const scopeId = `exec:${entry.id}`
      return {
        id: scopeId,
        request: entry,
        response: entry.result,
        rows: this.runtimeRows().filter(row => row.scopeId === scopeId),
      }
    })
  }

  runtimeBatches(by: 'entityId' | 'scopeId' | 'entityType' | 'kind' = 'entityId'): Record<string, RuntimeRow[]> {
    const batches: Record<string, RuntimeRow[]> = {}
    for (const row of this.runtimeRows()) {
      const key = String(row[by] ?? '')
      if (!batches[key]) batches[key] = []
      batches[key].push(row)
    }
    return batches
  }

  saveState(): SandboxSnapshot {
    return {
      version: 1,
      execLog: JSON.parse(JSON.stringify(this.execLog)) as ExecEntry[],
      serverState: JSON.parse(JSON.stringify(this.serverState)) as ServerNode[],
    }
  }

  loadState(snapshot: SandboxSnapshot): ExecResult {
    if (!snapshot || snapshot.version !== 1) {
      return { ok: false, error: 'loadState: unsupported snapshot version' }
    }
    if (!Array.isArray(snapshot.execLog) || !Array.isArray(snapshot.serverState)) {
      return { ok: false, error: 'loadState: invalid snapshot shape' }
    }

    this.execLog = JSON.parse(JSON.stringify(snapshot.execLog)) as ExecEntry[]
    this.serverState = JSON.parse(JSON.stringify(snapshot.serverState)) as ServerNode[]
    this.rebuildTree()
    this.rebuildFieldStore()
    this.notify()

    return {
      ok: true,
      data: {
        exec_count: this.execLog.length,
        node_count: this.tree.size,
      },
    }
  }

  diffState(before: SandboxSnapshot, after: SandboxSnapshot): SandboxDiff {
    const beforeSandbox = new Sandbox()
    beforeSandbox.loadState(before)

    const afterSandbox = new Sandbox()
    afterSandbox.loadState(after)

    return {
      execAdded: diffAdded(
        beforeSandbox.execLog.map((entry) => entry.id),
        afterSandbox.execLog.map((entry) => entry.id),
      ),
      execRemoved: diffAdded(
        afterSandbox.execLog.map((entry) => entry.id),
        beforeSandbox.execLog.map((entry) => entry.id),
      ),
      nodesAdded: diffAdded(
        Array.from(beforeSandbox.tree.keys()),
        Array.from(afterSandbox.tree.keys()),
      ),
      nodesRemoved: diffAdded(
        Array.from(afterSandbox.tree.keys()),
        Array.from(beforeSandbox.tree.keys()),
      ),
      fieldsAdded: diffAdded(
        Array.from(beforeSandbox.fieldStore.keys()),
        Array.from(afterSandbox.fieldStore.keys()),
      ),
      fieldsRemoved: diffAdded(
        Array.from(afterSandbox.fieldStore.keys()),
        Array.from(beforeSandbox.fieldStore.keys()),
      ),
      rowsAdded: diffAdded(
        beforeSandbox.runtimeRows().map((row) => row.rowId),
        afterSandbox.runtimeRows().map((row) => row.rowId),
      ),
      rowsRemoved: diffAdded(
        afterSandbox.runtimeRows().map((row) => row.rowId),
        beforeSandbox.runtimeRows().map((row) => row.rowId),
      ),
    }
  }

  runFromSnapshot(snapshot: SandboxSnapshot, op: string, args: Record<string, unknown> = {}, user = 'anon'): ReplayRunResult {
    const branch = new Sandbox()
    const loaded = branch.loadState(snapshot)
    if (!loaded.ok) {
      return {
        result: loaded,
        after: snapshot,
        diff: emptyDiff(),
      }
    }

    const result = branch.exec(op, args, user)
    const after = branch.saveState()
    const diff = this.diffState(snapshot, after)
    return { result, after, diff }
  }

  subscribe(fn: () => void): () => void {
    this.listeners.add(fn)
    return () => this.listeners.delete(fn)
  }

  private notify() {
    this.listeners.forEach(fn => fn())
  }

  toJSONL(): string {
    return this.execLog.map(e => JSON.stringify(e)).join('\n')
  }

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

const opMk: OpHandler = (sb, entry) => {
  const parent = (entry.args.parent as string) || ''
  const name = entry.args.name as string
  const type = entry.args.type as string | undefined
  if (!name) return { ok: false, error: 'mk: name required' }

  // Capability check: parent must have children[] scope open
  if (parent) {
    const parentNode = sb.tree.get(parent)
    if (!parentNode) return { ok: false, error: `mk: parent not found: ${parent}` }

    const cap = parentNode.capabilities
    if (!cap.children) {
      return { ok: false, error: `mk: scope closed — ${parent} has no children[] declared` }
    }
    // If children is string[] (specific types allowed), check type
    if (Array.isArray(cap.children) && type && !cap.children.includes(type)) {
      return { ok: false, error: `mk: type '${type}' not allowed in ${parent} (allowed: ${cap.children.join(', ')})` }
    }
  }

  const path = parent ? `${parent}/${name}` : name
  if (sb.tree.has(path)) return { ok: true, data: { path, exists: true } }

  // Derive capabilities from args or defaults
  const caps = (entry.args.capabilities as SandboxNode['capabilities']) ?? {}

  const node: SandboxNode = {
    name,
    path,
    type,
    meta: { type, user: entry.user, ts: new Date(entry.ts).toISOString() },
    data: (entry.args.data as Record<string, unknown>) ?? {},
    children: [],
    childLists: {},
    exec: [entry.id],
    capabilities: {
      exec: caps.exec ?? true,  // exec open by default
      children: caps.children,  // children closed by default (must declare)
      append: caps.append,
    },
  }
  sb.tree.set(path, node)

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
  entry.local = true
  return { ok: true, data: { path: entry.args.path } }
}

const opServerSync: OpHandler = (_sb, entry) => {
  entry.local = true
  return { ok: true, data: entry.args.result }
}

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

function valueTypeOf(value: unknown): string {
  if (Array.isArray(value)) return 'array'
  if (value === null) return 'null'
  return typeof value
}

function flattenValueLeaves(
  value: unknown,
  prefix: string,
): Array<{ path: string; name: string; value: unknown }> {
  const result: Array<{ path: string; name: string; value: unknown }> = []

  function walk(current: unknown, path: string) {
    if (Array.isArray(current)) {
      if (current.length === 0) {
        result.push({ path, name: path.split('.').pop() ?? path, value: current })
        return
      }
      current.forEach((item, index) => walk(item, path ? `${path}.${index}` : String(index)))
      return
    }
    if (current && typeof current === 'object') {
      const entries = Object.entries(current as Record<string, unknown>)
      if (entries.length === 0) {
        result.push({ path, name: path.split('.').pop() ?? path, value: current })
        return
      }
      for (const [key, next] of entries) {
        walk(next, path ? `${path}.${key}` : key)
      }
      return
    }
    result.push({ path, name: path.split('.').pop() ?? path, value: current })
  }

  walk(value, prefix)
  return result
}

function diffAdded(before: string[], after: string[]): string[] {
  const beforeSet = new Set(before)
  return after.filter((value) => !beforeSet.has(value)).sort(naturalSort)
}

function emptyDiff(): SandboxDiff {
  return {
    execAdded: [],
    execRemoved: [],
    nodesAdded: [],
    nodesRemoved: [],
    fieldsAdded: [],
    fieldsRemoved: [],
    rowsAdded: [],
    rowsRemoved: [],
  }
}

function childKinds(node: SandboxNode): string[] {
  const result = new Set<string>()
  if (node.type) result.add(node.type)
  const metaType = typeof node.meta.type === 'string' ? node.meta.type : undefined
  if (metaType) result.add(metaType)
  const prefix = node.name.match(/^([A-Za-z][\w-]*?)_\d+$/)?.[1]
  if (prefix) result.add(prefix)
  return Array.from(result)
}

function buildChildLists(tree: Map<string, SandboxNode>, parent: SandboxNode, childPaths: string[]): Record<string, string[]> {
  const lists: Record<string, string[]> = {}
  const declaredKinds = new Set<string>()

  if (Array.isArray(parent.capabilities.children)) {
    for (const kind of parent.capabilities.children) declaredKinds.add(kind)
  }
  if (parent.capabilities.append) {
    for (const [kind, allowed] of Object.entries(parent.capabilities.append)) {
      if (allowed) declaredKinds.add(kind)
    }
  }

  for (const kind of declaredKinds) {
    lists[kind] = []
  }

  for (const childPath of childPaths) {
    const child = tree.get(childPath)
    if (!child) continue
    for (const kind of childKinds(child)) {
      if (!lists[kind]) lists[kind] = []
      lists[kind].push(childPath)
    }
  }
  for (const refs of Object.values(lists)) {
    refs.sort(naturalSort)
  }
  return lists
}

function buildVirtualTemplateNode(parentPath: string, kind: string): SandboxNode {
  return {
    name: kind,
    path: parentPath ? `${parentPath}/${kind}` : kind,
    type: kind,
    meta: {
      type: kind,
      template: true,
      virtual: true,
      inherited: true,
    },
    data: {},
    children: [],
    childLists: {},
    exec: [],
    capabilities: capabilitiesFromType(kind),
  }
}

/** Derive default capabilities from node type */
function capabilitiesFromType(type?: string): SandboxNode['capabilities'] {
  switch (type) {
    // Root/pchat: open scope for any children
    case 'pchat':
      return { exec: true, children: true }
    // Channels container: children[] open for 'channel' type
    case 'channels':
      return { exec: true, children: ['channel'], append: { channel: true } }
    // Channel: children[] open for 'message' type
    case 'channel':
      return { exec: true, children: ['message'], append: { message: true } }
    // Message: exec open (can patch own fields), no children by default
    case 'message':
      return { exec: true }
    // Default: exec open, children closed
    default:
      return { exec: true }
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
