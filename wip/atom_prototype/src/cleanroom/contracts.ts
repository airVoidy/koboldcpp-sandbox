// Future-contracts and checkpoint-sync.
//
// FutureContract: declare a sync point in advance. Each peer prepares its own
// snapshot. At settle-time, all preparations are unioned into a keyframe —
// no principled merge, just co-presence (branching-as-default).
//
// CheckpointSync: predicate-over-exec-log. Watchers fire when log entries
// match a registered predicate. Sync-condition is just a predicate over the
// log, not a separate sync-protocol machine.
//
// See: docs/ATOMIC_CLEANROOM_ARCHITECTURE_SESSION_2026_04_22.md

import type { AtomicStore, AtomicSnapshot, JsonValue } from './store'

export type CheckpointPredicate = (entry: JsonValue) => boolean

export type FutureContractStatus = 'open' | 'settling' | 'settled' | 'cancelled'

export type FutureContract = {
  id: string
  declaredAt: number
  /** Optional human-meaningful target time. Not enforced. */
  scheduledAt?: number
  /** Map of peerId → prepared snapshot. */
  preparations: Map<string, AtomicSnapshot>
  /** Settled keyframe (union of preparations) once settle() is called. */
  keyframe?: KeyframeUnion
  status: FutureContractStatus
}

export type KeyframeUnion = {
  contractId: string
  settledAt: number
  peerIds: string[]
  /** Snapshot per peer. No merge — union. */
  snapshots: Record<string, AtomicSnapshot>
}

export class ContractRegistry {
  readonly contracts = new Map<string, FutureContract>()

  constructor(readonly store: AtomicStore) {}

  /** Declare a future contract; throws if id collides. */
  declare(id: string, scheduledAt?: number): FutureContract {
    if (this.contracts.has(id)) {
      throw new Error(`contract ${id} already declared`)
    }
    const contract: FutureContract = {
      id,
      declaredAt: Date.now(),
      scheduledAt,
      preparations: new Map(),
      status: 'open',
    }
    this.contracts.set(id, contract)
    return contract
  }

  /** Add or replace a peer's preparation. Contract must be open. */
  prepare(contractId: string, peerId: string, snapshot: AtomicSnapshot): FutureContract {
    const contract = this.requireOpen(contractId)
    contract.preparations.set(peerId, snapshot)
    return contract
  }

  /**
   * Settle: union current preparations into a keyframe. Does not require
   * all expected peers — settles with whoever prepared. Idempotent against
   * already-settled contracts (returns existing keyframe).
   */
  settle(contractId: string): KeyframeUnion {
    const contract = this.contracts.get(contractId)
    if (!contract) throw new Error(`contract ${contractId} not found`)

    if (contract.status === 'settled' && contract.keyframe) {
      return contract.keyframe
    }
    if (contract.status === 'cancelled') {
      throw new Error(`contract ${contractId} cancelled, cannot settle`)
    }

    contract.status = 'settling'

    const peerIds = [...contract.preparations.keys()]
    const snapshots: Record<string, AtomicSnapshot> = {}
    for (const peer of peerIds) {
      snapshots[peer] = contract.preparations.get(peer)!
    }

    const keyframe: KeyframeUnion = {
      contractId,
      settledAt: Date.now(),
      peerIds,
      snapshots,
    }
    contract.keyframe = keyframe
    contract.status = 'settled'
    return keyframe
  }

  /** Cancel an open contract. Cannot cancel settled. */
  cancel(contractId: string): void {
    const contract = this.contracts.get(contractId)
    if (!contract) return
    if (contract.status === 'settled') {
      throw new Error(`contract ${contractId} already settled, cannot cancel`)
    }
    contract.status = 'cancelled'
  }

  private requireOpen(contractId: string): FutureContract {
    const contract = this.contracts.get(contractId)
    if (!contract) throw new Error(`contract ${contractId} not found`)
    if (contract.status !== 'open') {
      throw new Error(`contract ${contractId} not open (status=${contract.status})`)
    }
    return contract
  }
}

export type CheckpointHandler = (entry: JsonValue, seq: number) => void

/**
 * Append-only exec-log with predicate-driven watchers. Watchers fire
 * synchronously when their predicate matches an appended entry.
 */
export class CheckpointSync {
  private watchers: Array<{
    id: string
    predicate: CheckpointPredicate
    handler: CheckpointHandler
  }> = []
  private log: JsonValue[] = []

  /** Append an entry; returns seq + matched watcher ids. */
  append(entry: JsonValue): { seq: number; matched: string[] } {
    this.log.push(entry)
    const seq = this.log.length
    const matched: string[] = []
    for (const w of this.watchers) {
      if (w.predicate(entry)) {
        try {
          w.handler(entry, seq)
        } catch {
          // handler errors are isolated; log entry remains appended
        }
        matched.push(w.id)
      }
    }
    return { seq, matched }
  }

  /** Register a predicate-driven watcher. Returns unwatch function. */
  watch(
    id: string,
    predicate: CheckpointPredicate,
    handler: CheckpointHandler,
  ): () => void {
    this.watchers.push({ id, predicate, handler })
    return () => this.unwatch(id)
  }

  unwatch(id: string): void {
    this.watchers = this.watchers.filter((w) => w.id !== id)
  }

  /** Read the entire log (for replay/inspection). */
  readLog(): ReadonlyArray<JsonValue> {
    return this.log
  }

  size(): number {
    return this.log.length
  }
}
