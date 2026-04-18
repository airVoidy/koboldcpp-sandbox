/**
 * Store — the op log + derived VirtualObject registry + per-object signals.
 *
 * Append-only log of FieldOps → source of truth.
 * VirtualObjects rebuilt from ops whenever touched.
 * Each object has a version Signal — bumps on any op affecting it.
 *
 * Sync-ready (Replicache-style):
 * - `snapshot(cookie)` returns delta since cookie
 * - `applyBatch(ops)` integrates remote ops (idempotent by {writer, seq})
 * - `writer` mandatory from day 1 (single-peer uses constant id)
 */
import type {
  Field,
  FieldOp,
  VirtualObject,
  ProjectionSpec,
  Cookie,
} from './types'
import { state, type Signal } from './signal'

export class Store {
  /** Append-only op log — canonical state. */
  private opLog: FieldOp[] = []

  /** Derived VirtualObject registry — rebuilt from ops. */
  private objects = new Map<string, VirtualObject>()

  /** Per-object version signals — bump on any op affecting the object. */
  private signals = new Map<string, Signal<number>>()

  /** Registered named projections. */
  private projections = new Map<string, ProjectionSpec>()

  /** Per-writer highest seq we've seen (for Replicache ack / rebase). */
  private lastSeqByWriter = new Map<string, number>()

  /** Cookie corresponds to opLog.length — simple monotonic cursor. */
  cookie(): number {
    return this.opLog.length
  }

  // ── Apply ops (local or remote) ──

  /**
   * Apply a single FieldOp.
   * Idempotent: duplicate (writer, seq) pairs are ignored.
   * Rebuilds the affected VirtualObject and bumps its signal.
   */
  apply(op: FieldOp): void {
    // Idempotency check — don't double-apply on remote echo
    const lastSeq = this.lastSeqByWriter.get(op.writer) ?? 0
    if (op.seq <= lastSeq) return

    this.opLog.push(op)
    this.lastSeqByWriter.set(op.writer, op.seq)

    this.rebuildObject(op.objectId)
    this.getSignal(op.objectId).update((v) => v + 1)
  }

  /** Apply a batch of ops atomically (Replicache push integrate). */
  applyBatch(ops: FieldOp[]): void {
    const touched = new Set<string>()
    for (const op of ops) {
      const lastSeq = this.lastSeqByWriter.get(op.writer) ?? 0
      if (op.seq <= lastSeq) continue
      this.opLog.push(op)
      this.lastSeqByWriter.set(op.writer, op.seq)
      touched.add(op.objectId)
    }
    for (const id of touched) {
      this.rebuildObject(id)
      this.getSignal(id).update((v) => v + 1)
    }
  }

  /**
   * Construct a FieldOp with auto-assigned seq for the given writer.
   * Convenience — callers can still build ops manually if needed.
   */
  makeOp(writer: string, partial: Omit<FieldOp, 'seq' | 'writer' | 'ts'>): FieldOp {
    const seq = (this.lastSeqByWriter.get(writer) ?? 0) + 1
    return {
      seq,
      writer,
      ts: new Date().toISOString(),
      ...partial,
    }
  }

  // ── Query ──

  get(id: string): VirtualObject | undefined {
    return this.objects.get(id)
  }

  /** Get all VirtualObjects — O(N), use sparingly. */
  all(): VirtualObject[] {
    return Array.from(this.objects.values())
  }

  /** Resolve an object through a named projection. */
  resolve(id: string, projectionName: string): Field[] {
    const obj = this.objects.get(id)
    if (!obj) return []
    const proj = this.projections.get(projectionName)
    if (!proj) throw new Error(`No projection registered: ${projectionName}`)
    return proj.resolve(obj, this)
  }

  // ── Projections ──

  registerProjection(spec: ProjectionSpec): void {
    this.projections.set(spec.name, spec)
  }

  /** List registered projection names. */
  projectionNames(): string[] {
    return Array.from(this.projections.keys())
  }

  // ── Signals / subscriptions ──

  /** Subscribe to any change on object `id`. Returns unsubscribe fn. */
  subscribe(id: string, cb: () => void): () => void {
    return this.getSignal(id).subscribe(cb)
  }

  /** Read the current version number for an object. */
  version(id: string): number {
    return this.signals.get(id)?.() ?? 0
  }

  private getSignal(id: string): Signal<number> {
    let sig = this.signals.get(id)
    if (!sig) {
      sig = state(0)
      this.signals.set(id, sig)
    }
    return sig
  }

  // ── Sync (Replicache-style) ──

  /**
   * Return ops since the given cookie.
   * Simple cursor = opLog array index.
   */
  snapshot(sinceCookie: Cookie = 0): { cookie: Cookie; ops: FieldOp[] } {
    const since = typeof sinceCookie === 'number' ? sinceCookie : 0
    return {
      cookie: this.opLog.length,
      ops: this.opLog.slice(since),
    }
  }

  /** Full op log — for debug / persist to JSONL. */
  allOps(): readonly FieldOp[] {
    return this.opLog
  }

  /** Per-writer acked seq — for rebase. */
  lastSeq(writer: string): number {
    return this.lastSeqByWriter.get(writer) ?? 0
  }

  // ── Object rebuild ──

  /**
   * Rebuild a VirtualObject from all ops affecting its id.
   * Called after every apply(). O(affected ops) per rebuild.
   */
  private rebuildObject(id: string): void {
    const fields = new Map<string, Field>()
    let virtualType = this.objects.get(id)?.virtualType ?? 'unknown'

    for (const op of this.opLog) {
      if (op.objectId !== id) continue
      if (op.fieldName === '_virtualType' && op.op === 'set') {
        virtualType = String(op.content ?? 'unknown')
        continue
      }
      if (op.op === 'unset') {
        fields.delete(op.fieldName)
      } else if (op.op === 'set') {
        fields.set(op.fieldName, {
          name: op.fieldName,
          type: op.type ?? 'value',
          content: op.content,
        })
      } else if (op.op === 'retype') {
        const existing = fields.get(op.fieldName)
        if (existing && op.type) {
          fields.set(op.fieldName, { ...existing, type: op.type })
        }
      }
    }

    const prev = this.objects.get(id)
    this.objects.set(id, {
      id,
      virtualType,
      fields,
      version: (prev?.version ?? 0) + 1,
    })
  }

  // ── Debug ──

  /** Serialize op log as JSONL (Langextract-compatible). */
  toJSONL(): string {
    return this.opLog.map((o) => JSON.stringify(o)).join('\n')
  }

  /** Hydrate from JSONL op log. */
  static fromJSONL(text: string): Store {
    const store = new Store()
    const lines = text.split('\n').filter((l) => l.trim())
    const ops = lines.map((l) => JSON.parse(l) as FieldOp)
    store.applyBatch(ops)
    return store
  }
}

// ── Built-in projections ──

/** Raw — returns fields as-is without transformation. */
export const RAW_PROJECTION: ProjectionSpec = {
  name: 'raw',
  resolve(obj) {
    return Array.from(obj.fields.values())
  },
}

/**
 * Serialize — resolves refs/paths/placeholders to concrete values.
 * Used for FS serialization: writing an object to disk should produce
 * self-contained JSON with no external pointers.
 */
export const SERIALIZE_PROJECTION: ProjectionSpec = {
  name: 'serialize',
  resolve(obj, store) {
    return Array.from(obj.fields.values()).map((f) => ({
      ...f,
      type: 'value' as const,
      content: resolveContentToValue(f, store),
    }))
  },
}

function resolveContentToValue(field: Field, store: ProjectionStoreLike): unknown {
  if (field.type === 'ref' && typeof field.content === 'string') {
    const target = store.get(field.content)
    if (!target) return null
    const fields: Record<string, unknown> = {}
    for (const [name, f] of target.fields) {
      fields[name] = resolveContentToValue(f, store)
    }
    return { _ref: field.content, fields }
  }
  // path/placeholder: for now, leave as-is (can extend later)
  return field.content
}

interface ProjectionStoreLike {
  get(id: string): VirtualObject | undefined
  resolve(id: string, name: string): Field[]
}
