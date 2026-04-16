/**
 * Runtime Object Layer types.
 *
 * Above Data Layer: each RuntimeObject has a `runtimeType` tag that selects
 * an adapter. Adapter delegates to library primitive (signal, lexical,
 * replicache, vfs, quickjs, crdt) or to Store (virtual).
 *
 * Design principle: polymorphism by naming, single common interface.
 * Consumers see `applyOp / read / subscribe / serialize / hydrate` —
 * library specifics hidden behind `B` generic.
 */
import type { Field, FieldOp, VirtualObject } from '@/data/types'

/**
 * Runtime type tag — which adapter handles this object's backend.
 *
 * - `virtual`: no separate backend; Store is direct source (lambda-on-resolve).
 * - `signal`: in-memory reactive state via signals micro-lib.
 * - `replicache`: server-authoritative with optimistic client + rebase (protocol).
 * - `lexical`: immutable NodeMap + double-buffer + transforms (rich docs).
 * - `vfs`: file-backed via just-bash InMemoryFs/OverlayFs (addressable files).
 * - `quickjs`: isolated QuickJS worker (untrusted code execution).
 * - `crdt`: SyncKit Fugue/Peritext (commutative merge, auto-convergence).
 */
export type RuntimeType =
  | 'virtual'
  | 'signal'
  | 'replicache'
  | 'lexical'
  | 'vfs'
  | 'quickjs'
  | 'crdt'

/**
 * Branch metadata for per-instance git sync.
 */
export interface BranchMeta {
  name: string          // e.g., "obj/msg_42/a3f9"
  baseRef: string       // parent commit hash
  divergedAt: number    // Store opLog index at branch creation
  auto: boolean         // was it auto-created
}

/**
 * RuntimeObject — wrapper around a VirtualObject id with adapter dispatch info.
 *
 * Multiple RuntimeObjects can reference the same VirtualObject (different
 * adapters viewing same data) but typically 1:1 inside a Store.
 */
export interface RuntimeObject {
  /** Matches VirtualObject.id in the underlying Store. */
  id: string
  /** Semantic type tag from template/schema ("message", "channel", ...). */
  virtualType: string
  /** Which adapter handles this object's backend. */
  runtimeType: RuntimeType
  /** Opaque per-type backend state. Only the matching adapter interprets it. */
  backend: unknown
  /** Per-type config (endpoint URL, branch name, subscriber list, ...). */
  config?: Record<string, unknown>
  /** Optional per-instance git branch for FS sync. */
  branch?: BranchMeta
  /** Which projection to use when serializing for FS (default 'serialize'). */
  serializationProjection?: string
}

/**
 * RuntimeAdapter — common interface all backends must implement.
 *
 * B = opaque backend type (Lexical editor, QuickJS worker, SyncKit doc, etc.)
 */
export interface RuntimeAdapter<B = unknown> {
  /** Create backend state for a new object. */
  create(
    id: string,
    virtualType: string,
    initial: Field[],
    config?: Record<string, unknown>,
  ): B

  /** Read current VirtualObject view from backend. */
  read(backend: B): VirtualObject

  /** Apply a FieldOp to the backend, producing side effects per its library semantics. */
  apply(backend: B, op: FieldOp): void

  /** Subscribe to backend changes. Returns unsubscribe fn. */
  subscribe(backend: B, cb: () => void): () => void

  /** Serialize backend state as FieldOp[] — for persistence / sync. */
  serialize(backend: B): FieldOp[]

  /** Reconstruct backend from FieldOp log. */
  hydrate(ops: FieldOp[], config?: Record<string, unknown>): B

  /** Optional cleanup (close workers, dispose editors, etc.). */
  dispose?(backend: B): void
}

/**
 * Template schema fields relevant for runtime resolution.
 *
 * Subset of root/templates/{type}/schema.json — just what runtime layer needs.
 * Full schema is read by server; client reads this subset via /query.
 */
export interface RuntimeTemplateSchema {
  type: string
  inherits?: string | null
  runtimeType?: RuntimeType
  runtimeConfig?: Record<string, unknown>
  serializationProjection?: string
  branchPolicy?: {
    auto?: boolean
    prefix?: string
  }
}
