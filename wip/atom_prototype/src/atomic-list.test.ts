import { describe, expect, it } from 'vitest'
import {
  ArrayAtomicList,
  NestedAtomicList,
  arrayList,
  computeAtomicHash,
  deriveSchema,
  nestedList,
  schemaKey,
  valueKey,
  valueEnvOf,
} from './atomic-list'

describe('schema derivation', () => {
  it('object: sorted relFields, localType=object', () => {
    expect(deriveSchema({ b: 2, a: 1 })).toEqual({ relFields: ['a', 'b'], localType: 'object' })
  })
  it('array: empty relFields, localType=array', () => {
    expect(deriveSchema([1, 2])).toEqual({ relFields: [], localType: 'array' })
  })
  it('primitives and null mapped to typeof / null', () => {
    expect(deriveSchema(42)).toEqual({ relFields: [], localType: 'number' })
    expect(deriveSchema('hi')).toEqual({ relFields: [], localType: 'string' })
    expect(deriveSchema(true)).toEqual({ relFields: [], localType: 'boolean' })
    expect(deriveSchema(null)).toEqual({ relFields: [], localType: 'null' })
  })
})

describe('hash key formation', () => {
  it('schemaKey format: <type>(<comma-joined fields>)', () => {
    expect(schemaKey({ relFields: ['a', 'b'], localType: 'object' })).toBe('object(a,b)')
    expect(schemaKey({ relFields: [], localType: 'number' })).toBe('number()')
  })

  it('valueKey format: <fieldValueType>:<deterministic JSON>', () => {
    expect(valueKey(valueEnvOf(42))).toBe('number:42')
    expect(valueKey(valueEnvOf('hi'))).toBe('string:"hi"')
    // Object keys sorted deterministically.
    expect(valueKey(valueEnvOf({ b: 2, a: 1 }))).toBe('object:{"a":1,"b":2}')
  })

  it('computeAtomicHash joins parts with "|"', () => {
    const h = computeAtomicHash({ name: 'alice', age: 30 })
    expect(h.schemaPart).toBe('object(age,name)')
    expect(h.valuePart).toBe('object:{"age":30,"name":"alice"}')
    expect(h.full).toBe(h.schemaPart + '|' + h.valuePart)
  })

  it('structurally equal values produce equal hashes', () => {
    const a = computeAtomicHash({ x: 1, y: 2 })
    const b = computeAtomicHash({ y: 2, x: 1 })
    expect(a.full).toBe(b.full)
  })

  it('caller-supplied fieldValueType overrides inferred type', () => {
    const h = computeAtomicHash(42, 'score')
    expect(h.valuePart).toBe('score:42')
  })
})

describe('ArrayAtomicList', () => {
  it('indices are positional, iteration preserves order', () => {
    const l = arrayList([10, 20, 30])
    expect(l.kind).toBe('array')
    expect(l.size).toBe(3)
    expect(l.keys()).toEqual([0, 1, 2])
    expect(l.items()).toEqual([10, 20, 30])
    expect(l.entries()).toEqual([[0, 10], [1, 20], [2, 30]])
  })

  it('get/has/add/remove operate by integer index', () => {
    const l = new ArrayAtomicList<number>()
    const k = l.add(100)
    expect(k).toBe(0)
    expect(l.get(0)).toBe(100)
    expect(l.has(0)).toBe(true)
    expect(l.has(1)).toBe(false)
    l.add(200)
    expect(l.size).toBe(2)
    expect(l.remove(0)).toBe(true)
    expect(l.items()).toEqual([200])
  })

  it('toJSON produces plain array', () => {
    expect(arrayList(['a', 'b']).toJSON()).toEqual(['a', 'b'])
  })

  it('toNested converts into NestedAtomicList with hash keys', () => {
    const a = arrayList([{ x: 1 }, { x: 2 }])
    const n = a.toNested()
    expect(n.kind).toBe('nested')
    expect(n.size).toBe(2)
    for (const key of n.keys()) {
      expect(key).toMatch(/^object\(x\)\|object:\{"x":\d\}$/)
    }
  })
})

describe('NestedAtomicList', () => {
  it('keys are hash strings formed from schema+value', () => {
    const l = nestedList([{ a: 1 }])
    expect(l.kind).toBe('nested')
    const [key] = l.keys()
    expect(key).toBe('object(a)|object:{"a":1}')
  })

  it('toJSON produces {"<hash>": item, ...}', () => {
    const l = nestedList([{ id: 1 }, { id: 2 }])
    const obj = l.toJSON()
    const keys = Object.keys(obj)
    expect(keys).toHaveLength(2)
    for (const k of keys) {
      expect(k).toMatch(/^object\(id\)\|object:\{"id":\d\}$/)
    }
  })

  it('dedup: adding same structural value twice keeps one slot', () => {
    const l = new NestedAtomicList<Record<string, number>>()
    const k1 = l.add({ x: 1, y: 2 })
    const k2 = l.add({ y: 2, x: 1 }) // same structure, different key order
    expect(k1).toBe(k2)
    expect(l.size).toBe(1)
  })

  it('hashOf returns decomposed schema+value pair for a stored key', () => {
    const l = new NestedAtomicList<unknown>()
    const key = l.add({ n: 7 })
    const h = l.hashOf(key)
    expect(h).toBeDefined()
    expect(h!.schemaPart).toBe('object(n)')
    expect(h!.valuePart).toBe('object:{"n":7}')
    expect(h!.full).toBe(key)
  })

  it('remove by key works; has/get respect string key', () => {
    const l = new NestedAtomicList<number>()
    const k = l.add(5)
    expect(l.has(k)).toBe(true)
    expect(l.get(k)).toBe(5)
    expect(l.remove(k)).toBe(true)
    expect(l.size).toBe(0)
  })

  it('toArray flattens back to positional list, preserving insertion order', () => {
    const n = nestedList([{ a: 1 }, { a: 2 }, { a: 3 }])
    const arr = n.toArray()
    expect(arr.kind).toBe('array')
    expect(arr.items().map((x) => (x as { a: number }).a)).toEqual([1, 2, 3])
  })

  it('custom fieldValueType propagates into hash valuePart', () => {
    const l = new NestedAtomicList<number>()
    l.add(42, 'score')
    const [k] = l.keys()
    expect(k).toContain('score:42')
  })
})

describe('interface parity', () => {
  it('both variants satisfy the shared base interface (items/keys/entries/size)', () => {
    const a = arrayList([1, 2, 3])
    const n = nestedList([1, 2, 3])

    expect(a.size).toBe(n.size)
    expect(a.items()).toEqual(n.items())
    expect(a.entries().length).toBe(n.entries().length)
    // keys differ in space (positional vs hash), parity is structural only.
  })
})
