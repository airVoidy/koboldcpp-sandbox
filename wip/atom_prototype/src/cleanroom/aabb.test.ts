import { describe, it, expect, beforeEach } from 'vitest'
import { AtomicStore, createAtomicList } from './store'
import { AabbLayout } from './aabb'

describe('AabbLayout', () => {
  let store: AtomicStore
  let layout: AabbLayout

  beforeEach(() => {
    store = new AtomicStore()
    store.putList(createAtomicList('list', ['a', 'b', 'c']))
    layout = new AabbLayout(store)
  })

  it('createLayout populates zone 0 with list items', () => {
    const l = layout.createLayout('lay', 'list')
    expect(l.zones['0'].items).toEqual(['a', 'b', 'c'])
    expect(l.zones['-1'].items).toEqual([])
    expect(l.zones['+1'].items).toEqual([])
  })

  it('createLayout fails for missing list', () => {
    expect(() => layout.createLayout('lay', 'absent')).toThrow(/not found/)
  })

  it('moveItem transfers between zones', () => {
    layout.createLayout('lay', 'list')
    const l = layout.moveItem('lay', 'a', 0, 1)
    expect(l.zones['0'].items).toEqual(['b', 'c'])
    expect(l.zones['+1'].items).toEqual(['a'])
  })

  it('moveItem throws when item not in source zone', () => {
    layout.createLayout('lay', 'list')
    expect(() => layout.moveItem('lay', 'a', 1, 0)).toThrow(/not in zone/)
  })

  it('checkpoint promotes from +1 to 0', () => {
    layout.createLayout('lay', 'list')
    layout.moveItem('lay', 'a', 0, 1)
    const l = layout.checkpoint('lay', 'a')
    expect(l.zones['0'].items).toContain('a')
    expect(l.zones['+1'].items).not.toContain('a')
  })

  it('archive demotes from 0 to -1', () => {
    layout.createLayout('lay', 'list')
    const l = layout.archive('lay', 'a')
    expect(l.zones['-1'].items).toContain('a')
    expect(l.zones['0'].items).not.toContain('a')
  })

  it('addToZone is idempotent', () => {
    layout.createLayout('lay', 'list')
    layout.addToZone('lay', 'x', 1)
    layout.addToZone('lay', 'x', 1)
    expect(layout.getLayout('lay')?.zones['+1'].items).toEqual(['x'])
  })

  it('removeFromZone is no-op for absent item', () => {
    layout.createLayout('lay', 'list')
    expect(() => layout.removeFromZone('lay', 'absent', 0)).not.toThrow()
  })

  it('setAabb stores bounding box', () => {
    layout.createLayout('lay', 'list')
    layout.setAabb('lay', 0, { x: 10, y: 20, w: 100, h: 50 })
    expect(layout.getLayout('lay')?.zones['0'].aabb).toEqual({ x: 10, y: 20, w: 100, h: 50 })
  })

  it('flatten returns items across zones in -1, 0, +1 order', () => {
    layout.createLayout('lay', 'list')
    layout.moveItem('lay', 'a', 0, -1)
    layout.moveItem('lay', 'c', 0, 1)
    expect(layout.flatten('lay')).toEqual(['a', 'b', 'c'])
  })

  it('zoneOf reports current zone of an item', () => {
    layout.createLayout('lay', 'list')
    layout.moveItem('lay', 'a', 0, -1)
    expect(layout.zoneOf('lay', 'a')).toBe(-1)
    expect(layout.zoneOf('lay', 'b')).toBe(0)
    expect(layout.zoneOf('lay', 'absent')).toBeNull()
  })

  it('checkpoint is no-op when item is not in +1', () => {
    layout.createLayout('lay', 'list')
    layout.checkpoint('lay', 'a')
    expect(layout.zoneOf('lay', 'a')).toBe(0)
  })
})
