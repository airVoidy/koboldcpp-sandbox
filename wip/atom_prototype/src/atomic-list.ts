/**
 * AtomicList — two variants of an atom collection:
 *
 *   - ArrayAtomicList   : positional index (0, 1, 2, ...), like [item, item, ...]
 *   - NestedAtomicList  : hash-keyed, each item wrapped as {"<hash>": item, ...}
 *
 * Same base interface, different key-space. Both iterate in insertion order.
 *
 * The nested variant's hash is a compound pair joined into a single field:
 *   - schema part: `<localType>(<sorted rel fields>)`
 *   - value part:  `<fieldValueType>:<JSON-encoded value>`
 *   - full:        `<schemaPart>|<valuePart>`
 *
 * Tree-resolvable: schema is literally a sorted list of relative field paths
 * + the local type. Value side carries typed value. Join is deterministic;
 * identical (schema, value) → identical hash → automatic dedup.
 *
 * No cryptographic hashing here — keys stay human-readable for debugging.
 * Swap in a real hash function (blake3, xxh3, sha-256) where identity needs
 * to be compact.
 */

export interface ListSchema {
  /** Sorted list of relative field paths present on the value. Empty for scalars. */
  relFields: string[]
  /** Local type name: 'object', 'array', 'number', 'string', 'boolean', 'null', ... */
  localType: string
}

export interface ListValueEnv {
  fieldValueType: string
  value: unknown
}

export interface AtomicHash {
  schemaPart: string
  valuePart: string
  /** Glued representation: "<schemaPart>|<valuePart>". Used as Map key. */
  full: string
}

/**
 * Minimum shared interface. Both variants satisfy this, so code that only
 * needs iteration / membership can accept either.
 */
export interface AtomicListBase<T> {
  readonly kind: 'array' | 'nested'
  readonly size: number
  items(): T[]
  /** Index for array; hash.full for nested. */
  keys(): Array<number | string>
  entries(): Array<[number | string, T]>
  get(key: number | string): T | undefined
  has(key: number | string): boolean
  /** Returns the key under which the item was stored. */
  add(item: T): number | string
  remove(key: number | string): boolean
  clear(): void
  /** Serializable shape — array literal or object-keyed-by-hash. */
  toJSON(): unknown
}

/* ------------------------------------------------------------------ */
/* Schema + hash derivation                                           */
/* ------------------------------------------------------------------ */

/**
 * Infer a light-weight schema from a runtime value. Deterministic:
 *   - object: keys sorted
 *   - array: relFields empty (positional), localType = 'array'
 *   - primitive: relFields empty, localType = typeof
 *   - null: localType = 'null'
 *
 * Not recursive — one level. Good enough for dedup of shallow shapes;
 * a deeper variant can land later if needed.
 */
export function deriveSchema(value: unknown): ListSchema {
  if (value === null) return { relFields: [], localType: 'null' }
  if (Array.isArray(value)) return { relFields: [], localType: 'array' }
  if (typeof value === 'object') {
    const obj = value as Record<string, unknown>
    return {
      relFields: Object.keys(obj).sort(),
      localType: 'object',
    }
  }
  return { relFields: [], localType: typeof value }
}

/** Stable string form of a schema for hashing/comparison. */
export function schemaKey(schema: ListSchema): string {
  return `${schema.localType}(${schema.relFields.join(',')})`
}

/**
 * Value side of the hash. `fieldValueType` defaults to the same string form
 * as schema's localType — this is intentional, matches the user's "Field
 * value type : value" formulation. Caller can override with a domain-specific
 * type label.
 */
export function valueEnvOf(value: unknown, fieldValueType?: string): ListValueEnv {
  return {
    fieldValueType: fieldValueType ?? deriveSchema(value).localType,
    value,
  }
}

export function valueKey(env: ListValueEnv): string {
  // Stable serialization. JSON.stringify handles primitives + containers
  // consistently; sorted object keys happen via deterministicStringify for
  // cross-run stability.
  return `${env.fieldValueType}:${deterministicStringify(env.value)}`
}

export function computeAtomicHash(value: unknown, fieldValueType?: string): AtomicHash {
  const schemaPart = schemaKey(deriveSchema(value))
  const env = valueEnvOf(value, fieldValueType)
  const valuePart = valueKey(env)
  return { schemaPart, valuePart, full: `${schemaPart}|${valuePart}` }
}

/** JSON.stringify that sorts object keys so equivalent shapes hash equal. */
function deterministicStringify(value: unknown): string {
  return JSON.stringify(value, (_key, v) => {
    if (v && typeof v === 'object' && !Array.isArray(v)) {
      const sorted: Record<string, unknown> = {}
      for (const k of Object.keys(v as Record<string, unknown>).sort()) {
        sorted[k] = (v as Record<string, unknown>)[k]
      }
      return sorted
    }
    return v
  })
}

/* ------------------------------------------------------------------ */
/* Array variant                                                      */
/* ------------------------------------------------------------------ */

export class ArrayAtomicList<T> implements AtomicListBase<T> {
  readonly kind = 'array'
  private data: T[] = []

  get size(): number {
    return this.data.length
  }

  items(): T[] {
    return [...this.data]
  }

  keys(): number[] {
    return this.data.map((_, i) => i)
  }

  entries(): Array<[number, T]> {
    return this.data.map((v, i) => [i, v] as [number, T])
  }

  get(key: number | string): T | undefined {
    const i = typeof key === 'number' ? key : Number(key)
    return Number.isInteger(i) && i >= 0 && i < this.data.length ? this.data[i] : undefined
  }

  has(key: number | string): boolean {
    const i = typeof key === 'number' ? key : Number(key)
    return Number.isInteger(i) && i >= 0 && i < this.data.length
  }

  add(item: T): number {
    this.data.push(item)
    return this.data.length - 1
  }

  remove(key: number | string): boolean {
    const i = typeof key === 'number' ? key : Number(key)
    if (!Number.isInteger(i) || i < 0 || i >= this.data.length) return false
    this.data.splice(i, 1)
    return true
  }

  clear(): void {
    this.data.length = 0
  }

  toJSON(): T[] {
    return [...this.data]
  }

  /** Convert this array list into a nested list. Hashes computed on add. */
  toNested(fieldValueTypeFor?: (item: T) => string): NestedAtomicList<T> {
    const out = new NestedAtomicList<T>()
    for (const item of this.data) {
      out.add(item, fieldValueTypeFor?.(item))
    }
    return out
  }
}

/* ------------------------------------------------------------------ */
/* Nested variant                                                     */
/* ------------------------------------------------------------------ */

export class NestedAtomicList<T> implements AtomicListBase<T> {
  readonly kind = 'nested'
  // Map preserves insertion order while keying by hash.full.
  private data = new Map<string, T>()
  // Track the computed hash per key so callers can inspect decomposition.
  private hashes = new Map<string, AtomicHash>()

  get size(): number {
    return this.data.size
  }

  items(): T[] {
    return [...this.data.values()]
  }

  keys(): string[] {
    return [...this.data.keys()]
  }

  entries(): Array<[string, T]> {
    return [...this.data.entries()]
  }

  get(key: number | string): T | undefined {
    return this.data.get(String(key))
  }

  has(key: number | string): boolean {
    return this.data.has(String(key))
  }

  /**
   * Add an item. If its computed hash already exists, the existing slot is
   * updated (dedup by structural equality). Returns the hash.full under
   * which the item lives.
   */
  add(item: T, fieldValueType?: string): string {
    const h = computeAtomicHash(item, fieldValueType)
    this.data.set(h.full, item)
    this.hashes.set(h.full, h)
    return h.full
  }

  remove(key: number | string): boolean {
    const k = String(key)
    const removed = this.data.delete(k)
    this.hashes.delete(k)
    return removed
  }

  clear(): void {
    this.data.clear()
    this.hashes.clear()
  }

  /** Retrieve the decomposed hash (schema + value parts) for a stored key. */
  hashOf(key: number | string): AtomicHash | undefined {
    return this.hashes.get(String(key))
  }

  /**
   * JSON shape: `{ "<hash>": item, ... }`. Exactly the nested-form literal
   * described in the architectural note.
   */
  toJSON(): Record<string, T> {
    const out: Record<string, T> = {}
    for (const [k, v] of this.data.entries()) out[k] = v
    return out
  }

  /** Convert this nested list into an array list. Order preserved. */
  toArray(): ArrayAtomicList<T> {
    const out = new ArrayAtomicList<T>()
    for (const v of this.data.values()) out.add(v)
    return out
  }
}

/* ------------------------------------------------------------------ */
/* Convenience factories                                              */
/* ------------------------------------------------------------------ */

export function arrayList<T>(initial?: Iterable<T>): ArrayAtomicList<T> {
  const out = new ArrayAtomicList<T>()
  if (initial) for (const v of initial) out.add(v)
  return out
}

export function nestedList<T>(initial?: Iterable<T>): NestedAtomicList<T> {
  const out = new NestedAtomicList<T>()
  if (initial) for (const v of initial) out.add(v)
  return out
}
