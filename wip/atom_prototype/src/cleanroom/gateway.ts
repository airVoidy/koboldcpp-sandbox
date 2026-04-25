// Atom-to-placeholder gateway: generalization of GloryHole over multiple
// payload shapes. The producer drops a typed payload (single value, ordered
// command sequence, time-series samples, stream reference), and the gateway
// routes to the first dispatcher matching the payload's kind + optional
// content predicate.
//
// The gateway only ROUTES — it does not interpret payload contents. The
// consumer (slot, atom, runtime view) decides what to do with a sequence
// vs timeseries vs single.
//
// Cardinality / temporality variants are kept as distinct payload kinds so
// downstream code can dispatch by shape without re-parsing.

import type { JsonValue } from './store'

export type SingleValuePayload = {
  kind: 'single'
  value: JsonValue
}

export type SequencePayload = {
  kind: 'sequence'
  /** Ordered commands, applied in array order by the consumer. */
  commands: JsonValue[]
}

export type TimeseriesSample = {
  at: number
  value: JsonValue
}

export type TimeseriesPayload = {
  kind: 'timeseries'
  /** Samples ordered by `at`. The gateway does not enforce ordering — it
   *  is the producer's responsibility (consumer may sort if needed). */
  samples: TimeseriesSample[]
}

export type StreamRefPayload = {
  kind: 'stream'
  /** Id of a StreamGate (or other channel addressable elsewhere). */
  channel: string
}

export type GatewayPayload =
  | SingleValuePayload
  | SequencePayload
  | TimeseriesPayload
  | StreamRefPayload

export type GatewayPayloadKind = GatewayPayload['kind']

export type GatewayDispatcher = {
  id: string
  /** Payload kind to match. '*' matches any kind. */
  matchKind: GatewayPayloadKind | '*'
  /** Optional secondary predicate on the full payload. */
  matchPayload?: (payload: GatewayPayload) => boolean
  /** Address of the consumer (slot id / atom id / scope id). */
  target: string
}

export type GatewayDropResult = {
  target: string
  dispatcherId: string
  payload: GatewayPayload
}

/**
 * AtomToPlaceholderGateway: type-routed drop point with multiple payload
 * shapes. First registered dispatcher whose matchKind+matchPayload accept
 * the payload wins (point-to-one). For point-to-many semantics over a
 * channel, use kind:'stream' and let the consumer subscribe to the
 * referenced StreamGate.
 */
export class AtomToPlaceholderGateway {
  private dispatchers: GatewayDispatcher[] = []

  registerDispatcher(dispatcher: GatewayDispatcher): void {
    this.dispatchers.push(dispatcher)
  }

  removeDispatcher(id: string): void {
    this.dispatchers = this.dispatchers.filter((d) => d.id !== id)
  }

  /**
   * Drop a payload. Returns the matched dispatch result, or null if no
   * dispatcher accepts the payload.
   */
  drop(payload: GatewayPayload): GatewayDropResult | null {
    for (const d of this.dispatchers) {
      if (d.matchKind !== '*' && d.matchKind !== payload.kind) continue
      if (d.matchPayload && !d.matchPayload(payload)) continue
      return { target: d.target, dispatcherId: d.id, payload }
    }
    return null
  }

  listDispatchers(): ReadonlyArray<{
    id: string
    matchKind: GatewayPayloadKind | '*'
    target: string
  }> {
    return this.dispatchers.map(({ id, matchKind, target }) => ({
      id,
      matchKind,
      target,
    }))
  }
}

/**
 * Convenience constructors for typed payloads. Optional — call sites can
 * also build payload objects literally.
 */
export const Payload = {
  single(value: JsonValue): SingleValuePayload {
    return { kind: 'single', value }
  },
  sequence(commands: JsonValue[]): SequencePayload {
    return { kind: 'sequence', commands }
  },
  timeseries(samples: TimeseriesSample[]): TimeseriesPayload {
    return { kind: 'timeseries', samples }
  },
  stream(channel: string): StreamRefPayload {
    return { kind: 'stream', channel }
  },
}
