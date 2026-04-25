import { describe, it, expect } from 'vitest'
import { MemoryStorageBackend, isOpfsAvailable } from './storage'

describe('MemoryStorageBackend', () => {
  it('put/get roundtrip', async () => {
    const s = new MemoryStorageBackend()
    await s.put('a', { v: 1 })
    expect(await s.get('a')).toEqual({ v: 1 })
  })

  it('get returns undefined for missing key', async () => {
    const s = new MemoryStorageBackend()
    expect(await s.get('absent')).toBeUndefined()
  })

  it('list returns all keys when no prefix', async () => {
    const s = new MemoryStorageBackend()
    await s.put('a', 1)
    await s.put('b', 2)
    await s.put('c', 3)
    expect((await s.list()).sort()).toEqual(['a', 'b', 'c'])
  })

  it('list filters by prefix', async () => {
    const s = new MemoryStorageBackend()
    await s.put('snap:1', 'a')
    await s.put('snap:2', 'b')
    await s.put('other:1', 'c')
    expect((await s.list('snap:')).sort()).toEqual(['snap:1', 'snap:2'])
  })

  it('delete removes entry', async () => {
    const s = new MemoryStorageBackend()
    await s.put('a', 1)
    await s.delete('a')
    expect(await s.get('a')).toBeUndefined()
    expect(s.size()).toBe(0)
  })

  it('delete is no-op for missing key', async () => {
    const s = new MemoryStorageBackend()
    await expect(s.delete('absent')).resolves.toBeUndefined()
  })

  it('overwrites on second put', async () => {
    const s = new MemoryStorageBackend()
    await s.put('a', 1)
    await s.put('a', 2)
    expect(await s.get('a')).toBe(2)
    expect(s.size()).toBe(1)
  })
})

describe('isOpfsAvailable', () => {
  it('returns false in node test environment (no navigator.storage)', () => {
    // vitest defaults to node env; OPFS isn't there.
    expect(isOpfsAvailable()).toBe(false)
  })
})
