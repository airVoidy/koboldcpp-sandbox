import { describe, expect, it } from 'vitest'
import { Namescope, NamescopeCell, makeNamescope } from './namescope'

const mk = (hash: string, type = 't', payload: unknown = null) => ({
  hash,
  type,
  payload,
})

describe('Namescope — virtual type catalog', () => {
  it('register + get by hash', () => {
    const ns = new Namescope()
    ns.registerType(mk('h1', 'msg'))
    expect(ns.has('h1')).toBe(true)
    expect(ns.get('h1')?.type).toBe('msg')
    expect(ns.size()).toBe(1)
  })

  it('unregister removes the entry', () => {
    const ns = new Namescope()
    ns.registerType(mk('h1'))
    expect(ns.unregisterType('h1')).toBe(true)
    expect(ns.has('h1')).toBe(false)
  })

  it('filter / sort / pick operate on catalog entries', () => {
    const ns = new Namescope()
    ns.registerType(mk('a', 'msg', { order: 3 }))
    ns.registerType(mk('b', 'channel', { order: 1 }))
    ns.registerType(mk('c', 'msg', { order: 2 }))

    expect(ns.filter((e) => e.type === 'msg').map((e) => e.hash)).toEqual(['a', 'c'])
    expect(
      ns.sort((x, y) => (x.payload as { order: number }).order - (y.payload as { order: number }).order).map((e) => e.hash),
    ).toEqual(['b', 'c', 'a'])
    expect(ns.pick((e) => e.type === 'channel')?.hash).toBe('b')
  })
})

describe('Namescope — alias projection', () => {
  it('setSharedAlias requires registered hash', () => {
    const ns = new Namescope()
    expect(() => ns.setSharedAlias('x', 'ghost')).toThrow(/not registered/)
  })

  it('setPersonalAlias requires registered hash', () => {
    const ns = new Namescope()
    expect(() => ns.setPersonalAlias('cell1', 'x', 'ghost')).toThrow(/not registered/)
  })

  it('shared alias resolves without cellId', () => {
    const ns = new Namescope()
    ns.registerType(mk('h1'))
    ns.setSharedAlias('foo', 'h1')
    expect(ns.resolve('foo')).toBe('h1')
  })

  it('personal alias requires cellId to resolve', () => {
    const ns = new Namescope()
    ns.registerType(mk('h1'))
    ns.setPersonalAlias('cellA', 'foo', 'h1')
    // Without cellId → shared only (nothing shared) → undefined
    expect(ns.resolve('foo')).toBeUndefined()
    // With correct cellId → resolved
    expect(ns.resolve('foo', 'cellA')).toBe('h1')
    // With different cellId → undefined (personal aliases isolated per cell)
    expect(ns.resolve('foo', 'cellB')).toBeUndefined()
  })

  it('personal takes precedence over shared for same name', () => {
    const ns = new Namescope()
    ns.registerType(mk('h1'))
    ns.registerType(mk('h2'))
    ns.setSharedAlias('foo', 'h1')
    ns.setPersonalAlias('cellA', 'foo', 'h2')

    // Without cellId → shared (h1)
    expect(ns.resolve('foo')).toBe('h1')
    // With cellA → personal wins (h2)
    expect(ns.resolve('foo', 'cellA')).toBe('h2')
    // With other cell → shared (h1)
    expect(ns.resolve('foo', 'cellB')).toBe('h1')
  })

  it('forgetCell wipes personal alias space for that cell only', () => {
    const ns = new Namescope()
    ns.registerType(mk('h1'))
    ns.setPersonalAlias('cellA', 'foo', 'h1')
    ns.setPersonalAlias('cellB', 'foo', 'h1')
    expect(ns.forgetCell('cellA')).toBe(true)
    expect(ns.resolve('foo', 'cellA')).toBeUndefined()
    expect(ns.resolve('foo', 'cellB')).toBe('h1')
  })
})

describe('NamescopeCell — consumer with its own personal space', () => {
  it('aliasLocal + resolve are personal', () => {
    const { ns, cell } = makeNamescope()
    ns.registerType(mk('h1'))

    const c = cell('cell-1')
    c.aliasLocal('foo', 'h1')
    expect(c.resolve('foo')).toBe('h1')
    // Another cell doesn't see it
    expect(cell('cell-2').resolve('foo')).toBeUndefined()
  })

  it('aliasShared visible from any cell', () => {
    const { cell, ns } = makeNamescope()
    ns.registerType(mk('h1'))

    const c1 = cell('c1')
    c1.aliasShared('foo', 'h1')
    expect(cell('c2').resolve('foo')).toBe('h1')
  })

  it('personal alias shadows shared for that cell only', () => {
    const { cell, ns } = makeNamescope()
    ns.registerType(mk('h1'))
    ns.registerType(mk('h2'))

    const c1 = cell('c1')
    c1.aliasShared('foo', 'h1')
    const c2 = cell('c2')
    c2.aliasLocal('foo', 'h2')

    expect(c1.resolve('foo')).toBe('h1')
    expect(c2.resolve('foo')).toBe('h2')
  })

  it('deref hydrates to full virtual type entry', () => {
    const { cell, ns } = makeNamescope()
    ns.registerType(mk('h1', 'msg', { body: 'hello' }))
    const c = cell('c1')
    c.aliasLocal('greet', 'h1')
    expect(c.deref('greet')).toEqual({ hash: 'h1', type: 'msg', payload: { body: 'hello' } })
  })

  it('cells delegate filter/sort/pick to namescope', () => {
    const { cell, ns } = makeNamescope()
    ns.registerType(mk('a', 'msg', { n: 2 }))
    ns.registerType(mk('b', 'channel', { n: 1 }))
    ns.registerType(mk('c', 'msg', { n: 3 }))

    const c = cell('c1')
    expect(c.filter((e) => e.type === 'msg').map((e) => e.hash)).toEqual(['a', 'c'])
    expect(c.sort((x, y) => (x.payload as { n: number }).n - (y.payload as { n: number }).n).map((e) => e.hash)).toEqual(['b', 'a', 'c'])
    expect(c.pick((e) => e.type === 'channel')?.hash).toBe('b')
  })

  it('cell disposal via removePersonalAlias does not affect shared or other cells', () => {
    const { cell, ns } = makeNamescope()
    ns.registerType(mk('h1'))
    const c1 = cell('c1')
    const c2 = cell('c2')
    c1.aliasShared('g', 'h1')
    c1.aliasLocal('local1', 'h1')
    c2.aliasLocal('local1', 'h1')

    expect(c1.removePersonalAlias('local1')).toBe(true)
    expect(c1.resolve('local1')).toBeUndefined()
    expect(c2.resolve('local1')).toBe('h1')
    expect(c1.resolve('g')).toBe('h1') // shared alias untouched
  })
})

describe('one-way architecture invariant', () => {
  it('Namescope does not track cells — cell disposal is opaque', () => {
    // Create a cell, set personal, let it go out of scope, verify Namescope still
    // carries the aliases until forgetCell() is explicitly called. This proves
    // the one-way relationship: cells live independently, Namescope doesn't
    // hold references to cell instances.
    const { cell, ns } = makeNamescope()
    ns.registerType(mk('h1'))
    {
      const c = new NamescopeCell('temp', ns)
      c.aliasLocal('x', 'h1')
    }
    // Cell object gone; personal aliases still there until forgetCell()
    expect(ns.resolve('x', 'temp')).toBe('h1')
    ns.forgetCell('temp')
    expect(ns.resolve('x', 'temp')).toBeUndefined()
    void cell // ref used to silence lints
  })
})
