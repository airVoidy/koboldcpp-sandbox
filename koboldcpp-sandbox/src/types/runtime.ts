/**
 * Runtime types — mirrors Python atomic runtime model.
 *
 * Source of truth: immutable exec log (L0)
 * All objects are projections over canonical fields.
 */

/** Canonical field — runtime singleton by path */
export interface Field {
  /** Canonical atomic-dsl path = identity */
  path: string
  /** Current resolved value */
  value: unknown
  /** Hash for cheap equality / sync */
  hash?: string
}

/** Flat field table entry: [hash, path, value] */
export type FieldEntry = [string, string, unknown]

/** Exec log entry — L0 immutable record */
export interface ExecEntry {
  op: string
  user: string
  ts: string
  args?: Record<string, unknown>
  /** Resolved batch of sub-operations */
  batch?: ExecEntry[]
}

/** Runtime Node — container of local exec/messages/patches */
export interface RuntimeNode {
  /** Node identity path */
  path: string
  /** Type from template */
  type?: string
  /** Local exec log (append-only) */
  exec: ExecEntry[]
  /** Canonical fields owned by this node */
  fields: Record<string, Field>
}

/** Projection field entry (server format) */
export interface ProjectionFieldRow {
  hash: string
  path: string
  value: unknown
}

/** Projection — derived view over fields (mirrors server _build_message_projection) */
export interface Projection {
  /** Source node path */
  source_node: string
  /** Meta scope */
  _meta: { global_path: string; schema: Record<string, string>; value: Record<string, unknown> }
  /** Data scope */
  _data: { global_path: string; schema: Record<string, string>; value: Record<string, unknown> }
  /** All field entries */
  fields: Array<{
    hash: string; scope: string; path: string
    full_relative_path: string; bind: string
    value: unknown; value_type: string
  }>
  /** Flat field store: path → [hash, path, value] */
  flat_store: Record<string, FieldEntry>
  /** View filters: view_name → list of paths */
  view_filters: Record<string, string[]>
  /** Named views: view_name → rows of {hash, path, value} */
  views: Record<string, ProjectionFieldRow[]>
}

/** Template aggregation result (from /mproject) */
export interface TemplateAggregation {
  ok: boolean
  type: string
  scope: string
  count: number
  instances: Array<{ id: string; path: string; meta: Record<string, unknown> }>
  flat_store: Record<string, FieldEntry>
  fields: Array<{ instance: string; path: string; namespaced_path: string; hash: string; value: unknown }>
  instance_views: Record<string, Record<string, ProjectionFieldRow[]>>
}

/** Runtime container state as rows + patch_log (not mutable state.json) */
export interface ContainerRuntime {
  id: string
  /** Canonical rows (atomic-dsl format) */
  rows: Array<Record<string, unknown>>
  /** Append-only patch log */
  patch_log: ExecEntry[]
  /** Optional manifest for resolve rules */
  manifest?: Record<string, unknown>
}

/**
 * L0/L1/L2 layer model:
 * - L0 = immutable exec/messages/patches
 * - L1 = rows / linked runtime field layer
 * - L2 = resolved serializations (lists, tables, cards, trees)
 */

// ── JSONata-compatible path utilities ──

/** Resolve dot-path on object (JSONata `.` step) */
export function getByPath(obj: unknown, path: string): unknown {
  let cur = obj
  for (const part of path.split('.')) {
    if (cur == null || typeof cur !== 'object') return undefined
    cur = (cur as Record<string, unknown>)[part]
  }
  return cur
}

/** Set value at dot-path */
export function setByPath(obj: Record<string, unknown>, path: string, value: unknown): void {
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

/** $spread equivalent — object → array of {key, value} */
export function spread(obj: Record<string, unknown>): Array<{ key: string; value: unknown }> {
  return Object.entries(obj).map(([key, value]) => ({ key, value }))
}

/** $merge equivalent — array of objects → merged object */
export function merge(arr: Array<Record<string, unknown>>): Record<string, unknown> {
  return Object.assign({}, ...arr)
}

/** $keys equivalent */
export function keys(obj: unknown): string[] {
  if (obj == null || typeof obj !== 'object') return []
  return Object.keys(obj)
}

/** Build flat field store from object (like flatten_json) */
export function toFieldStore(
  obj: Record<string, unknown>,
  prefix = '',
): Record<string, FieldEntry> {
  const store: Record<string, FieldEntry> = {}

  function walk(val: unknown, path: string) {
    if (val != null && typeof val === 'object' && !Array.isArray(val)) {
      for (const [k, v] of Object.entries(val as Record<string, unknown>)) {
        walk(v, path ? `${path}.${k}` : k)
      }
    } else {
      // Leaf — create field entry [hash, path, value]
      const hash = simpleHash(`${path}:${JSON.stringify(val)}`)
      store[path] = [hash, path, val]
    }
  }

  walk(obj, prefix)
  return store
}

/** Reconstruct object from flat field store (like rows_to_json) */
export function fromFieldStore(store: Record<string, FieldEntry>): Record<string, unknown> {
  const result: Record<string, unknown> = {}
  for (const [, [, path, value]] of Object.entries(store)) {
    setByPath(result, path, value)
  }
  return result
}

/** Apply patch to field store (L1 operation) */
export function patchFieldStore(
  store: Record<string, FieldEntry>,
  path: string,
  value: unknown,
): Record<string, FieldEntry> {
  const hash = simpleHash(`${path}:${JSON.stringify(value)}`)
  return { ...store, [path]: [hash, path, value] }
}

/** Simple string hash for field identity */
function simpleHash(str: string): string {
  let h = 0
  for (let i = 0; i < str.length; i++) {
    h = ((h << 5) - h + str.charCodeAt(i)) | 0
  }
  return h.toString(36)
}
