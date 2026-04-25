// Sync bridge: bind CheckpointSync to a StorageBackend so snapshots are
// persisted automatically when log entries match a predicate.
//
// This is the practical wire-up: "state checkpoints are synced at specific
// point ↔ hash of specific pattern" — predicate-over-exec-log triggering
// snapshot persistence. The backend chooses where snapshots actually live
// (memory / OPFS / anything else implementing StorageBackend).

import type { AtomicSnapshot, AtomicStore, JsonValue } from './store'
import type { CheckpointPredicate, CheckpointSync } from './contracts'
import type { StorageBackend } from './storage'

export type SnapshotOnCheckpointOptions = {
  /** Watcher id on the CheckpointSync. */
  watcherId: string
  /** Match log entries that should trigger a snapshot. */
  predicate: CheckpointPredicate
  /** Pick the AtomicStore target id from the matched entry. */
  target: (entry: JsonValue, seq: number) => string
  /** Build the storage key from the matched entry. */
  keyOf: (entry: JsonValue, seq: number) => string
  /** Optional: receive errors raised during async storage put. */
  onError?: (err: unknown, ctx: { entry: JsonValue; seq: number; key: string }) => void
}

/**
 * Bind a CheckpointSync to a StorageBackend: when an appended entry matches
 * `predicate`, snapshot the AtomicStore around `target(entry, seq)` and
 * persist it under `keyOf(entry, seq)` via the backend.
 *
 * Returns an `unbind` function that removes the watcher from the sync.
 *
 * Storage put is async; the watcher is fire-and-forget. Use `onError` to
 * surface failures or `await` the returned promise via a flush loop.
 */
export function bindSnapshotOnCheckpoint(
  sync: CheckpointSync,
  store: AtomicStore,
  storage: StorageBackend,
  opts: SnapshotOnCheckpointOptions,
): () => void {
  const pending = new Set<Promise<void>>()

  const unwatch = sync.watch(opts.watcherId, opts.predicate, (entry, seq) => {
    const targetId = opts.target(entry, seq)
    const key = opts.keyOf(entry, seq)
    const snapshot = store.snapshot(targetId)

    const job = storage
      .put(key, snapshot as unknown as JsonValue)
      .catch((err: unknown) => {
        if (opts.onError) {
          opts.onError(err, { entry, seq, key })
        }
      })
      .finally(() => {
        pending.delete(job)
      })

    pending.add(job)
  })

  return () => {
    unwatch()
  }
}

/**
 * Restore the most recently-stored snapshot matching a key prefix.
 * Useful for "resume from last checkpoint" scenarios.
 *
 * Note: this only RETURNS the snapshot object. It does not mutate the
 * AtomicStore — that's the caller's responsibility, since restoring is
 * scope-dependent.
 */
export async function loadLatestSnapshot(
  storage: StorageBackend,
  prefix: string,
): Promise<AtomicSnapshot | undefined> {
  const keys = await storage.list(prefix)
  if (keys.length === 0) return undefined

  // Keys may include createdAt or seq numerically; we sort lexicographically
  // and take the last. Callers using time-based keys should choose key
  // shapes that sort correctly (e.g., ISO timestamps or zero-padded seqs).
  keys.sort()
  const latestKey = keys[keys.length - 1]
  const value = await storage.get(latestKey)
  if (!value) return undefined
  return value as unknown as AtomicSnapshot
}
