/**
 * Data Layer types — FieldOp log + derived VirtualObject + Projection.
 *
 * The ONE primitive: FieldOp (mutation on a field). Everything else derived.
 *
 * Designed to be compatible with:
 * - Replicache push/pull (per-writer monotonic seq, cookie-based delta)
 * - Lexical-style immutable snapshots (VirtualObject rebuilt per change)
 * - Langextract JSONL (FieldOp serializes 1-line-per-entry)
 * - Signals (per-object version signal for push notifications)
 */

/**
 * Field type tag — determines how `content` is interpreted.
 *
 * Base types:
 * - 'value' — content is the literal value
 * - 'ref' — content is an object id (points to another VirtualObject)
 * - 'path_rel' — content is a relative dot-path string
 * - 'path_abs' — content is an absolute atomic path from root
 * - 'placeholder' — content is a descriptor for lazy resolve
 *
 * Custom types allowed (string) — projections decide how to resolve them.
 */
export type FieldType =
  | 'value'
  | 'ref'
  | 'path_rel'
  | 'path_abs'
  | 'placeholder'
  | string

/** A single field on a VirtualObject. */
export interface Field {
  name: string
  type: FieldType
  content: unknown
}

/**
 * FieldOp — the only primitive. Everything else is derived view.
 *
 * Append-only log of FieldOps = canonical state.
 * VirtualObjects are rebuilt from ops affecting their id.
 *
 * For sync (Replicache-style):
 * - `seq` is monotonic per `writer`
 * - Server acks up to `lastMutationID` per writer
 * - Pull delta = ops since cookie
 * - Rebase: drop ops with seq <= ack, replay remaining
 */
export interface FieldOp {
  /** Monotonic per `writer` — critical for Replicache rebase. */
  seq: number
  /** Agent/user/peer id. Never null — even single-peer uses constant id. */
  writer: string
  /** ISO timestamp. */
  ts: string
  /** Target VirtualObject id. */
  objectId: string
  /** Target field name within object. */
  fieldName: string
  /** Mutation kind. */
  op: 'set' | 'unset' | 'retype'
  /** Field type for 'set' / 'retype'. */
  type?: FieldType
  /** Field content for 'set'. */
  content?: unknown
  /** Causality link — op that caused this one (cross-object, cross-writer). */
  cause?: { writer: string; seq: number }
}

/**
 * VirtualObject — derived view from FieldOps.
 *
 * Never constructed directly — Store rebuilds from opLog.
 * `version` bumps on any op affecting this id. Subscribers listen on signal.
 */
export interface VirtualObject {
  id: string
  /** Semantic type tag: "channel", "message", "worker", "card". */
  virtualType: string
  /** Resolved fields by name, derived from ops. */
  fields: Map<string, Field>
  /** Bumps on every op. Used by signals + React useSyncExternalStore. */
  version: number
}

/**
 * Projection — named pure function over a VirtualObject.
 *
 * Produces a transformed Field[] — may inline refs/paths to values,
 * filter fields, add overlay fields, etc. Pure → cacheable, sandbox-executable.
 */
export interface ProjectionSpec {
  name: string
  resolve(obj: VirtualObject, store: ProjectionStore): Field[]
}

/**
 * Subset of Store API accessible from within a ProjectionSpec.resolve.
 * Keeps projections pure (read-only view).
 */
export interface ProjectionStore {
  get(id: string): VirtualObject | undefined
  resolve(id: string, projectionName: string): Field[]
}

/**
 * VirtualList — ordered list of refs to other objects, with optional per-item projection.
 *
 * Not its own primitive — modeled as a VirtualObject with field type='ref' list content.
 * Helper type for clarity where list-of-refs is the common pattern (messages in channel).
 */
export interface VirtualList {
  id: string
  items: Array<{ id: string; projection?: string }>
}

/**
 * Cookie for Replicache-style pull delta identification.
 * Opaque to client; server-generated ordering token.
 */
export type Cookie = string | number | { order: string | number }
