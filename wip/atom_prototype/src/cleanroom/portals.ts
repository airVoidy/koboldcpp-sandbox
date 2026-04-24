// Portal-семейство: GloryHole + StreamGate.
//
// GloryHole: point-to-one drop with type-routed dispatch. Producer doesn't know
// which destination will catch — first matching dispatcher wins.
//
// StreamGate: point-to-many emit, unlimited subscribers. Each subscriber is
// independent (one's failure doesn't affect others).
//
// Both are peer primitives in the same family, differing in cardinality.
// See architectural notes in docs/ATOMIC_CLEANROOM_ARCHITECTURE_SESSION_2026_04_22.md

import type { AtomicStore, JsonValue } from './store'

export type DropMatcher = (payload: JsonValue) => boolean

export type DropResult = { target: string; dispatcherId: string }

/**
 * GloryHole: declare dispatchers ahead of time, drop a payload and let the
 * first matching dispatcher catch it. Cardinality: point-to-one.
 */
export class GloryHole {
  private dispatchers: Array<{
    id: string
    match: DropMatcher
    target: string
  }> = []

  /** Register a dispatcher. Order matters: first match wins. */
  registerDispatcher(id: string, match: DropMatcher, target: string): void {
    this.dispatchers.push({ id, match, target })
  }

  removeDispatcher(id: string): void {
    this.dispatchers = this.dispatchers.filter((d) => d.id !== id)
  }

  /** Drop a payload. Returns matched target or null when nothing matches. */
  drop(payload: JsonValue): DropResult | null {
    for (const d of this.dispatchers) {
      if (d.match(payload)) {
        return { target: d.target, dispatcherId: d.id }
      }
    }
    return null
  }

  /** Inspect declared dispatchers (read-only view). */
  listDispatchers(): ReadonlyArray<{ id: string; target: string }> {
    return this.dispatchers.map(({ id, target }) => ({ id, target }))
  }
}

export type StreamMeta = { gateId: string; seq: number }
export type StreamSubscriber = (payload: JsonValue, meta: StreamMeta) => void

export type EmitResult = { seq: number; delivered: number; failed: number }

/**
 * StreamGate: emit once, deliver to all current subscribers. Cardinality:
 * point-to-many. Subscriber errors are isolated (counted as `failed`, do
 * not stop other subscribers).
 */
export class StreamGate {
  private subscribers = new Map<string, StreamSubscriber>()
  private seq = 0

  constructor(readonly id: string) {}

  /** Subscribe; returns an unsubscribe function. */
  subscribe(subscriberId: string, fn: StreamSubscriber): () => void {
    this.subscribers.set(subscriberId, fn)
    return () => this.unsubscribe(subscriberId)
  }

  unsubscribe(subscriberId: string): void {
    this.subscribers.delete(subscriberId)
  }

  /** Emit a payload to all subscribers. Errors counted, not propagated. */
  emit(payload: JsonValue): EmitResult {
    const seq = ++this.seq
    let delivered = 0
    let failed = 0
    for (const [, fn] of this.subscribers) {
      try {
        fn(payload, { gateId: this.id, seq })
        delivered++
      } catch {
        failed++
      }
    }
    return { seq, delivered, failed }
  }

  size(): number {
    return this.subscribers.size
  }
}

/**
 * PortalRegistry: convenience holder for GloryHole and StreamGate instances
 * keyed by string id, alongside an AtomicStore. Lazily creates instances.
 */
export class PortalRegistry {
  private holes = new Map<string, GloryHole>()
  private gates = new Map<string, StreamGate>()

  constructor(readonly store: AtomicStore) {}

  gloryHole(id: string): GloryHole {
    let h = this.holes.get(id)
    if (!h) {
      h = new GloryHole()
      this.holes.set(id, h)
    }
    return h
  }

  streamGate(id: string): StreamGate {
    let g = this.gates.get(id)
    if (!g) {
      g = new StreamGate(id)
      this.gates.set(id, g)
    }
    return g
  }

  hasGloryHole(id: string): boolean {
    return this.holes.has(id)
  }

  hasStreamGate(id: string): boolean {
    return this.gates.has(id)
  }
}
