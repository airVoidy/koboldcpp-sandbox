/**
 * Runtime types — mirrors server atomic runtime model.
 *
 * Source of truth: immutable exec log (L0) + immutable server responses.
 * All objects are projections over canonical fields.
 */

/** Atomic runtime data object: path ↔ value pair */
export interface Row {
  path: string
  value: unknown
}

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
  /** Unique id */
  id: string
  /** Operation name */
  op: string
  /** Who issued */
  user: string
  /** Timestamp ISO */
  ts: string
  /** Operation arguments */
  args?: Record<string, unknown>
  /** Server response (immutable) */
  result?: unknown
  /** True = client-only, no server call */
  local?: boolean
  /** Resolved batch of sub-operations */
  batch?: ExecEntry[]
}

/** Server node (from /api/pchat/view response) — immutable */
export interface ServerNode {
  name: string
  path: string
  meta: Record<string, unknown>
  data: Record<string, unknown>
}

/** Runtime Node — projection over server + local data */
export interface RuntimeNode {
  /** Node identity path */
  path: string
  /** Name (last path segment) */
  name: string
  /** Type from template */
  type?: string
  /** Meta fields */
  meta: Record<string, unknown>
  /** Data fields */
  data: Record<string, unknown>
  /** Child paths (refs, not objects) */
  children: string[]
  /** Exec entry IDs relevant to this node */
  exec: string[]
}

// ── JSONata-compatible path utilities ──

/** Resolve dot-path on object */
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
      const hash = simpleHash(`${path}:${JSON.stringify(val)}`)
      store[path] = [hash, path, val]
    }
  }

  walk(obj, prefix)
  return store
}

/** Reconstruct object from flat field store */
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
