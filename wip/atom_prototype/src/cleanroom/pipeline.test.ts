import { describe, it, expect, beforeEach } from 'vitest'
import {
  AtomicStore,
  createAtomicObject,
  createAtomicRule,
  createProjectionSlot,
} from './store'
import { ProjectionPipeline } from './pipeline'

describe('ProjectionPipeline', () => {
  let store: AtomicStore
  let pipeline: ProjectionPipeline

  beforeEach(() => {
    store = new AtomicStore()
    pipeline = new ProjectionPipeline(store)
  })

  it('resolves a literal vector to materialized', () => {
    store.putObject(createAtomicObject('o', null))
    store.declareSlot(createProjectionSlot('s', 'o', { kind: 'literal', value: 42 }))

    const result = pipeline.resolveSlot('s')

    expect(result.state).toBe('materialized')
    expect(result.value).toBe(42)
  })

  it('treats raw (non-dispatch) vector as itself', () => {
    store.putObject(createAtomicObject('o', null))
    store.declareSlot(createProjectionSlot('s', 'o', 'hello'))

    const result = pipeline.resolveSlot('s')

    expect(result.state).toBe('materialized')
    expect(result.value).toBe('hello')
  })

  it('resolves slotRef recursively', () => {
    store.putObject(createAtomicObject('o', null))
    store.declareSlot(createProjectionSlot('a', 'o', { kind: 'literal', value: 1 }))
    store.declareSlot(createProjectionSlot('b', 'o', { kind: 'slotRef', slotId: 'a' }))

    const result = pipeline.resolveSlot('b')

    expect(result.state).toBe('materialized')
    expect(result.value).toBe(1)
    expect(store.slots.get('a')?.state).toBe('materialized')
  })

  it('marks problem on missing slotRef', () => {
    store.putObject(createAtomicObject('o', null))
    store.declareSlot(createProjectionSlot('s', 'o', { kind: 'slotRef', slotId: 'missing' }))

    const result = pipeline.resolveSlot('s')

    expect(result.state).toBe('problem')
    expect(pipeline.getError('s')).toMatch(/missing/)
  })

  it('applies registered rule resolver', () => {
    pipeline.registerRuleResolver('double', (body) => {
      const value = (body as { value: number }).value
      return value * 2
    })

    store.putObject(createAtomicObject('o', null))
    store.attachRule('o', createAtomicRule('r', { kind: 'double', value: 21 }))
    store.declareSlot(createProjectionSlot('s', 'o', { kind: 'rule', ruleKind: 'double' }))

    const result = pipeline.resolveSlot('s')

    expect(result.state).toBe('materialized')
    expect(result.value).toBe(42)
  })

  it('marks problem when no resolver registered', () => {
    store.putObject(createAtomicObject('o', null))
    store.attachRule('o', createAtomicRule('r', { kind: 'unknown' }))
    store.declareSlot(createProjectionSlot('s', 'o', { kind: 'rule', ruleKind: 'unknown' }))

    const result = pipeline.resolveSlot('s')

    expect(result.state).toBe('problem')
    expect(pipeline.getError('s')).toMatch(/no resolver/)
  })

  it('marks problem when no attached rule of kind', () => {
    pipeline.registerRuleResolver('double', () => 0)
    store.putObject(createAtomicObject('o', null))
    store.declareSlot(createProjectionSlot('s', 'o', { kind: 'rule', ruleKind: 'double' }))

    const result = pipeline.resolveSlot('s')

    expect(result.state).toBe('problem')
    expect(pipeline.getError('s')).toMatch(/no attached rule/)
  })

  it('compose resolves array of inputs', () => {
    store.putObject(createAtomicObject('o', null))
    store.declareSlot(createProjectionSlot('a', 'o', { kind: 'literal', value: 1 }))
    store.declareSlot(createProjectionSlot('b', 'o', { kind: 'literal', value: 2 }))
    store.declareSlot(
      createProjectionSlot('c', 'o', {
        kind: 'compose',
        inputs: [
          { kind: 'slotRef', slotId: 'a' },
          { kind: 'slotRef', slotId: 'b' },
        ],
      }),
    )

    const result = pipeline.resolveSlot('c')

    expect(result.state).toBe('materialized')
    expect(result.value).toEqual([1, 2])
  })

  it('is idempotent on already-materialized slot', () => {
    store.putObject(createAtomicObject('o', null))
    store.declareSlot(createProjectionSlot('s', 'o', { kind: 'literal', value: 10 }))

    const first = pipeline.resolveSlot('s')
    const second = pipeline.resolveSlot('s')

    expect(first.state).toBe('materialized')
    expect(second.state).toBe('materialized')
    expect(second.value).toBe(10)
  })

  it('forkShadow creates declared variant inheriting vector', () => {
    store.putObject(createAtomicObject('o', null))
    store.declareSlot(createProjectionSlot('s', 'o', { kind: 'literal', value: 100 }))
    pipeline.resolveSlot('s')

    const shadow = pipeline.forkShadow('s', 's.shadow')

    expect(shadow.state).toBe('declared')
    expect(shadow.owner).toBe('o')
    expect(shadow.vector).toEqual({ kind: 'literal', value: 100 })
  })

  it('shadow variant resolved with asShadow ends in shadow state', () => {
    store.putObject(createAtomicObject('o', null))
    store.declareSlot(createProjectionSlot('s', 'o', { kind: 'literal', value: 100 }))

    pipeline.forkShadow('s', 's.shadow', {
      vectorOverride: { kind: 'literal', value: 200 },
    })

    const result = pipeline.resolveSlot('s.shadow', { asShadow: true })

    expect(result.state).toBe('shadow')
    expect(result.value).toBe(200)
  })

  it('detects resolution cycles — both slots end in problem, inner catches cycle', () => {
    store.putObject(createAtomicObject('o', null))
    store.declareSlot(createProjectionSlot('a', 'o', { kind: 'slotRef', slotId: 'b' }))
    store.declareSlot(createProjectionSlot('b', 'o', { kind: 'slotRef', slotId: 'a' }))

    const result = pipeline.resolveSlot('a')

    expect(result.state).toBe('problem')
    expect(store.slots.get('b')?.state).toBe('problem')
    // The inner slot (b) catches the cycle directly when it tries to ref back to a (which is 'resolving').
    expect(pipeline.getError('b')).toMatch(/cycle|resolving/i)
  })
})
