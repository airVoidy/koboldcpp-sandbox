import { describe, it, expect, beforeEach } from 'vitest'
import { AtomicStore } from './store'
import { GloryHole, StreamGate, PortalRegistry } from './portals'

describe('GloryHole', () => {
  it('routes payload to first matching dispatcher', () => {
    const h = new GloryHole()
    h.registerDispatcher('numbers', (p) => typeof p === 'number', 'slot:numbers')
    h.registerDispatcher('strings', (p) => typeof p === 'string', 'slot:strings')

    expect(h.drop(42)).toEqual({ target: 'slot:numbers', dispatcherId: 'numbers' })
    expect(h.drop('hi')).toEqual({ target: 'slot:strings', dispatcherId: 'strings' })
  })

  it('returns null when no dispatcher matches', () => {
    const h = new GloryHole()
    h.registerDispatcher('nums', (p) => typeof p === 'number', 't')
    expect(h.drop('hi')).toBeNull()
  })

  it('removeDispatcher removes routing', () => {
    const h = new GloryHole()
    h.registerDispatcher('any', () => true, 't')
    h.removeDispatcher('any')
    expect(h.drop(1)).toBeNull()
  })

  it('uses first matcher when multiple match', () => {
    const h = new GloryHole()
    h.registerDispatcher('first', () => true, 'slot:first')
    h.registerDispatcher('second', () => true, 'slot:second')
    expect(h.drop(0)?.dispatcherId).toBe('first')
  })

  it('listDispatchers returns id+target view', () => {
    const h = new GloryHole()
    h.registerDispatcher('a', () => true, 'ta')
    h.registerDispatcher('b', () => false, 'tb')
    expect(h.listDispatchers()).toEqual([
      { id: 'a', target: 'ta' },
      { id: 'b', target: 'tb' },
    ])
  })
})

describe('StreamGate', () => {
  it('delivers emitted payload to all subscribers', () => {
    const g = new StreamGate('g')
    const received: unknown[] = []
    g.subscribe('s1', (p) => received.push(p))
    g.subscribe('s2', (p) => received.push(p))

    const result = g.emit('hi')
    expect(result.delivered).toBe(2)
    expect(received).toEqual(['hi', 'hi'])
  })

  it('subscriber error is isolated, others still receive', () => {
    const g = new StreamGate('g')
    const seen: number[] = []
    g.subscribe('bad', () => {
      throw new Error('boom')
    })
    g.subscribe('good', (p) => seen.push(Number(p)))

    const result = g.emit(7)
    expect(result.delivered).toBe(1)
    expect(result.failed).toBe(1)
    expect(seen).toEqual([7])
  })

  it('unsubscribe stops delivery', () => {
    const g = new StreamGate('g')
    const seen: number[] = []
    const unsub = g.subscribe('s', (p) => seen.push(Number(p)))
    g.emit(1)
    unsub()
    g.emit(2)
    expect(seen).toEqual([1])
  })

  it('seq increments per emit', () => {
    const g = new StreamGate('g')
    expect(g.emit(null).seq).toBe(1)
    expect(g.emit(null).seq).toBe(2)
  })

  it('size reflects subscriber count', () => {
    const g = new StreamGate('g')
    expect(g.size()).toBe(0)
    g.subscribe('a', () => undefined)
    g.subscribe('b', () => undefined)
    expect(g.size()).toBe(2)
  })

  it('meta carries gateId and seq', () => {
    const g = new StreamGate('mygate')
    let captured: { gateId: string; seq: number } | null = null
    g.subscribe('s', (_p, m) => {
      captured = m
    })
    g.emit('x')
    expect(captured).toEqual({ gateId: 'mygate', seq: 1 })
  })
})

describe('PortalRegistry', () => {
  let registry: PortalRegistry
  beforeEach(() => {
    registry = new PortalRegistry(new AtomicStore())
  })

  it('gloryHole returns same instance on repeat call', () => {
    const a = registry.gloryHole('h')
    const b = registry.gloryHole('h')
    expect(a).toBe(b)
  })

  it('streamGate returns same instance on repeat call', () => {
    const a = registry.streamGate('g')
    const b = registry.streamGate('g')
    expect(a).toBe(b)
  })

  it('reports presence for both portal types', () => {
    expect(registry.hasGloryHole('x')).toBe(false)
    registry.gloryHole('x')
    expect(registry.hasGloryHole('x')).toBe(true)

    expect(registry.hasStreamGate('y')).toBe(false)
    registry.streamGate('y')
    expect(registry.hasStreamGate('y')).toBe(true)
  })
})
