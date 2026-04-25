import { describe, it, expect, beforeEach } from 'vitest'
import {
  AtomicStore,
  createAtomicObject,
  type JsonValue,
} from './store'
import { CheckpointSync } from './contracts'
import { MemoryStorageBackend } from './storage'
import { bindSnapshotOnCheckpoint, loadLatestSnapshot } from './sync_bridge'

describe('bindSnapshotOnCheckpoint', () => {
  let store: AtomicStore
  let sync: CheckpointSync
  let storage: MemoryStorageBackend

  beforeEach(() => {
    store = new AtomicStore()
    store.putObject(createAtomicObject('o', { v: 1 }))
    sync = new CheckpointSync()
    storage = new MemoryStorageBackend()
  })

  it('persists snapshot when predicate matches', async () => {
    bindSnapshotOnCheckpoint(sync, store, storage, {
      watcherId: 'snap',
      predicate: (e: JsonValue) => {
        const entry = e as { kind?: string } | null
        return entry !== null && typeof entry === 'object' && entry.kind === 'checkpoint'
      },
      target: () => 'o',
      keyOf: (_e, seq) => `snap:${String(seq).padStart(6, '0')}`,
    })

    sync.append({ kind: 'op', payload: 1 })
    sync.append({ kind: 'checkpoint', label: 'c1' })

    // bridge is fire-and-forget; flush microtasks
    await new Promise((r) => setTimeout(r, 0))

    const keys = await storage.list('snap:')
    expect(keys).toHaveLength(1)
    const snap = await storage.get(keys[0])
    expect(snap).toBeTruthy()
    expect((snap as { target: string }).target).toBe('o')
  })

  it('skips non-matching entries', async () => {
    bindSnapshotOnCheckpoint(sync, store, storage, {
      watcherId: 'snap',
      predicate: () => false,
      target: () => 'o',
      keyOf: () => 'never',
    })

    sync.append({ kind: 'op' })
    sync.append({ kind: 'op' })
    await new Promise((r) => setTimeout(r, 0))

    expect(await storage.list()).toHaveLength(0)
  })

  it('unbind stops further snapshots', async () => {
    const unbind = bindSnapshotOnCheckpoint(sync, store, storage, {
      watcherId: 'snap',
      predicate: () => true,
      target: () => 'o',
      keyOf: (_e, seq) => `s:${seq}`,
    })

    sync.append('first')
    await new Promise((r) => setTimeout(r, 0))
    expect(await storage.list()).toHaveLength(1)

    unbind()
    sync.append('second')
    await new Promise((r) => setTimeout(r, 0))
    expect(await storage.list()).toHaveLength(1)
  })

  it('uses different snapshot targets per matched entry', async () => {
    store.putObject(createAtomicObject('targetA', { v: 'A' }))
    store.putObject(createAtomicObject('targetB', { v: 'B' }))

    bindSnapshotOnCheckpoint(sync, store, storage, {
      watcherId: 'snap',
      predicate: () => true,
      target: (e) => (e as { target: string }).target,
      keyOf: (e) => `snap:${(e as { target: string }).target}`,
    })

    sync.append({ target: 'targetA' })
    sync.append({ target: 'targetB' })
    await new Promise((r) => setTimeout(r, 0))

    const a = (await storage.get('snap:targetA')) as { target: string } | undefined
    const b = (await storage.get('snap:targetB')) as { target: string } | undefined
    expect(a?.target).toBe('targetA')
    expect(b?.target).toBe('targetB')
  })
})

describe('loadLatestSnapshot', () => {
  it('returns the lexicographically-last snapshot under a prefix', async () => {
    const storage = new MemoryStorageBackend()
    await storage.put('snap:000001', { id: 's1', target: 'o' })
    await storage.put('snap:000002', { id: 's2', target: 'o' })
    await storage.put('snap:000003', { id: 's3', target: 'o' })
    await storage.put('other:1', { id: 'x', target: 'o' })

    const latest = await loadLatestSnapshot(storage, 'snap:')
    expect(latest).toBeTruthy()
    expect((latest as { id: string }).id).toBe('s3')
  })

  it('returns undefined when no entries under prefix', async () => {
    const storage = new MemoryStorageBackend()
    expect(await loadLatestSnapshot(storage, 'snap:')).toBeUndefined()
  })
})
