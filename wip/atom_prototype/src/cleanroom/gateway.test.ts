import { describe, it, expect } from 'vitest'
import { AtomToPlaceholderGateway, Payload } from './gateway'

describe('AtomToPlaceholderGateway', () => {
  it('routes single payload to single-kind dispatcher', () => {
    const g = new AtomToPlaceholderGateway()
    g.registerDispatcher({ id: 'd', matchKind: 'single', target: 'slot:a' })

    const result = g.drop(Payload.single(42))
    expect(result).toEqual({
      target: 'slot:a',
      dispatcherId: 'd',
      payload: { kind: 'single', value: 42 },
    })
  })

  it('routes sequence payload to sequence-kind dispatcher', () => {
    const g = new AtomToPlaceholderGateway()
    g.registerDispatcher({ id: 's', matchKind: 'sequence', target: 'slot:cmds' })

    const result = g.drop(Payload.sequence([{ op: 'a' }, { op: 'b' }]))
    expect(result?.target).toBe('slot:cmds')
    expect(result?.payload.kind).toBe('sequence')
  })

  it('routes timeseries payload to timeseries-kind dispatcher', () => {
    const g = new AtomToPlaceholderGateway()
    g.registerDispatcher({ id: 't', matchKind: 'timeseries', target: 'slot:metrics' })

    const result = g.drop(
      Payload.timeseries([
        { at: 1, value: 10 },
        { at: 2, value: 20 },
      ]),
    )
    expect(result?.target).toBe('slot:metrics')
  })

  it('routes stream payload to stream-kind dispatcher', () => {
    const g = new AtomToPlaceholderGateway()
    g.registerDispatcher({ id: 'st', matchKind: 'stream', target: 'gate:events' })

    const result = g.drop(Payload.stream('events'))
    expect(result?.target).toBe('gate:events')
    if (result?.payload.kind === 'stream') {
      expect(result.payload.channel).toBe('events')
    }
  })

  it('wildcard matchKind accepts any payload kind', () => {
    const g = new AtomToPlaceholderGateway()
    g.registerDispatcher({ id: 'any', matchKind: '*', target: 'sink' })

    expect(g.drop(Payload.single(1))?.target).toBe('sink')
    expect(g.drop(Payload.sequence([]))?.target).toBe('sink')
    expect(g.drop(Payload.timeseries([]))?.target).toBe('sink')
    expect(g.drop(Payload.stream('x'))?.target).toBe('sink')
  })

  it('matchPayload narrows beyond kind', () => {
    const g = new AtomToPlaceholderGateway()
    g.registerDispatcher({
      id: 'big-numbers',
      matchKind: 'single',
      matchPayload: (p) => p.kind === 'single' && typeof p.value === 'number' && p.value > 100,
      target: 'slot:big',
    })

    expect(g.drop(Payload.single(50))).toBeNull()
    expect(g.drop(Payload.single(150))?.target).toBe('slot:big')
  })

  it('first matching dispatcher wins', () => {
    const g = new AtomToPlaceholderGateway()
    g.registerDispatcher({ id: 'first', matchKind: '*', target: 't1' })
    g.registerDispatcher({ id: 'second', matchKind: '*', target: 't2' })

    expect(g.drop(Payload.single(0))?.dispatcherId).toBe('first')
  })

  it('returns null when no dispatcher matches', () => {
    const g = new AtomToPlaceholderGateway()
    g.registerDispatcher({ id: 's', matchKind: 'single', target: 't' })

    expect(g.drop(Payload.sequence([]))).toBeNull()
  })

  it('removeDispatcher removes routing', () => {
    const g = new AtomToPlaceholderGateway()
    g.registerDispatcher({ id: 'x', matchKind: '*', target: 't' })
    g.removeDispatcher('x')
    expect(g.drop(Payload.single(0))).toBeNull()
  })

  it('listDispatchers returns kind+target view', () => {
    const g = new AtomToPlaceholderGateway()
    g.registerDispatcher({ id: 'a', matchKind: 'single', target: 'ta' })
    g.registerDispatcher({ id: 'b', matchKind: 'sequence', target: 'tb' })

    expect(g.listDispatchers()).toEqual([
      { id: 'a', matchKind: 'single', target: 'ta' },
      { id: 'b', matchKind: 'sequence', target: 'tb' },
    ])
  })

  it('Payload helpers produce correctly-shaped objects', () => {
    expect(Payload.single(1)).toEqual({ kind: 'single', value: 1 })
    expect(Payload.sequence([{ x: 1 }])).toEqual({
      kind: 'sequence',
      commands: [{ x: 1 }],
    })
    expect(Payload.timeseries([{ at: 0, value: 'a' }])).toEqual({
      kind: 'timeseries',
      samples: [{ at: 0, value: 'a' }],
    })
    expect(Payload.stream('ch')).toEqual({ kind: 'stream', channel: 'ch' })
  })
})
