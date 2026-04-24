import { describe, it, expect, beforeEach } from 'vitest'
import { AtomicStore, createAtomicObject, type JsonValue } from './store'
import { ContractRegistry, CheckpointSync } from './contracts'

describe('ContractRegistry', () => {
  let store: AtomicStore
  let registry: ContractRegistry

  beforeEach(() => {
    store = new AtomicStore()
    store.putObject(createAtomicObject('o', { v: 1 }))
    registry = new ContractRegistry(store)
  })

  it('declares a future contract in open status', () => {
    const c = registry.declare('c1')
    expect(c.status).toBe('open')
    expect(c.preparations.size).toBe(0)
  })

  it('rejects double declaration', () => {
    registry.declare('c1')
    expect(() => registry.declare('c1')).toThrow(/already declared/)
  })

  it('peers prepare snapshots independently', () => {
    registry.declare('c1')
    const snap = store.snapshot('o')
    registry.prepare('c1', 'peerA', snap)
    expect(registry.contracts.get('c1')!.preparations.get('peerA')).toBe(snap)
  })

  it('settles into keyframe-union of preparations', () => {
    registry.declare('c1')
    const snapA = store.snapshot('o')
    const snapB = store.snapshot('o')
    registry.prepare('c1', 'peerA', snapA)
    registry.prepare('c1', 'peerB', snapB)

    const keyframe = registry.settle('c1')
    expect(keyframe.peerIds.sort()).toEqual(['peerA', 'peerB'])
    expect(keyframe.snapshots.peerA).toBe(snapA)
    expect(keyframe.snapshots.peerB).toBe(snapB)
    expect(registry.contracts.get('c1')!.status).toBe('settled')
  })

  it('settles even with partial preparations (union, not consensus)', () => {
    registry.declare('c1')
    registry.prepare('c1', 'peerA', store.snapshot('o'))
    const keyframe = registry.settle('c1')
    expect(keyframe.peerIds).toEqual(['peerA'])
  })

  it('settle is idempotent — returns same keyframe on second call', () => {
    registry.declare('c1')
    registry.prepare('c1', 'p', store.snapshot('o'))
    const first = registry.settle('c1')
    const second = registry.settle('c1')
    expect(second).toBe(first)
  })

  it('cannot prepare on settled contract', () => {
    registry.declare('c1')
    registry.settle('c1')
    expect(() => registry.prepare('c1', 'p', store.snapshot('o'))).toThrow(/not open/)
  })

  it('cancel marks status, prevents preparations', () => {
    registry.declare('c1')
    registry.cancel('c1')
    expect(registry.contracts.get('c1')!.status).toBe('cancelled')
    expect(() => registry.prepare('c1', 'p', store.snapshot('o'))).toThrow(/not open/)
  })

  it('cannot cancel already-settled contract', () => {
    registry.declare('c1')
    registry.settle('c1')
    expect(() => registry.cancel('c1')).toThrow(/already settled/)
  })

  it('cannot settle cancelled contract', () => {
    registry.declare('c1')
    registry.cancel('c1')
    expect(() => registry.settle('c1')).toThrow(/cancelled/)
  })
})

describe('CheckpointSync', () => {
  let sync: CheckpointSync

  beforeEach(() => {
    sync = new CheckpointSync()
  })

  it('append fires watchers whose predicate matches', () => {
    const matched: number[] = []
    sync.watch(
      'odd',
      (e) => typeof e === 'number' && e % 2 === 1,
      (_e, s) => matched.push(s),
    )

    sync.append(2)
    sync.append(3)
    sync.append(5)

    expect(matched).toEqual([2, 3])
  })

  it('returns matched watcher ids on append', () => {
    sync.watch('a', () => true, () => undefined)
    sync.watch('b', () => false, () => undefined)
    const result = sync.append('hi')
    expect(result.matched).toEqual(['a'])
  })

  it('unwatch removes watcher', () => {
    let count = 0
    const stop = sync.watch('w', () => true, () => {
      count++
    })
    sync.append(1)
    stop()
    sync.append(2)
    expect(count).toBe(1)
  })

  it('readLog returns full append history', () => {
    sync.append(1)
    sync.append('two')
    expect(sync.readLog()).toEqual([1, 'two'])
  })

  it('size matches readLog length', () => {
    expect(sync.size()).toBe(0)
    sync.append(null)
    expect(sync.size()).toBe(1)
  })

  it('seq is monotonic per append', () => {
    expect(sync.append(0).seq).toBe(1)
    expect(sync.append(0).seq).toBe(2)
    expect(sync.append(0).seq).toBe(3)
  })

  it('handler errors do not break append flow', () => {
    sync.watch('bad', () => true, () => {
      throw new Error('boom')
    })
    expect(() => sync.append('x')).not.toThrow()
    expect(sync.size()).toBe(1)
  })

  it('checkpoint pattern: hash-of-pattern as predicate', () => {
    type LogEntry = { kind: string; payload: JsonValue }
    const captured: LogEntry[] = []

    sync.watch(
      'sync-on-checkpoint',
      (e: JsonValue) => {
        const entry = e as { kind?: unknown } | null
        return entry !== null && typeof entry === 'object' && entry.kind === 'checkpoint'
      },
      (e) => captured.push(e as LogEntry),
    )

    sync.append({ kind: 'op', payload: 1 })
    sync.append({ kind: 'checkpoint', payload: 'snap' })
    sync.append({ kind: 'op', payload: 2 })
    sync.append({ kind: 'checkpoint', payload: 'snap2' })

    expect(captured).toHaveLength(2)
    expect((captured[0] as LogEntry).payload).toBe('snap')
    expect((captured[1] as LogEntry).payload).toBe('snap2')
  })
})

