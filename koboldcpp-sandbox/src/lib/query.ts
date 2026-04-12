/**
 * JSONata query/transform layer.
 *
 * Runtime bindings from sandbox fieldStore, not endpoint responses.
 * Same jsonata-python on server, same jsonata npm on client.
 * One expression, two runtimes.
 */
import jsonata from 'jsonata'
import type { FieldEntry } from '@/types/runtime'
import { getByPath, toFieldStore, fromFieldStore } from '@/types/runtime'
import type { FieldCell } from './sandbox'

/** Pre-compiled expression cache */
const cache = new Map<string, jsonata.Expression>()

function compile(expr: string): jsonata.Expression {
  let compiled = cache.get(expr)
  if (!compiled) {
    compiled = jsonata(expr)
    cache.set(expr, compiled)
  }
  return compiled
}

/** Runtime lambda bindings using sandbox fieldStore */
function createBindings(fieldStore?: Map<string, FieldCell>) {
  return {
    /** $field(path) — get field cell from sandbox fieldStore */
    field: (path: string): FieldCell | undefined => {
      return fieldStore?.get(path)
    },

    /** $value(path) — get resolved value from fieldStore */
    value: (path: string): unknown => {
      return fieldStore?.get(path)?.value
    },

    /** $keys_of(obj) — shorthand for Object.keys */
    keys_of: (obj: unknown): string[] => {
      if (obj && typeof obj === 'object') return Object.keys(obj)
      return []
    },

    /** $flatten(obj) — object → flat field store */
    flatten: (obj: Record<string, unknown>): Record<string, FieldEntry> => {
      return toFieldStore(obj)
    },

    /** $unflatten(store) — flat field store → object */
    unflatten: (store: Record<string, FieldEntry>): Record<string, unknown> => {
      return fromFieldStore(store)
    },

    /** $get(obj, path) — dot-path access */
    get: (obj: unknown, path: string): unknown => {
      return getByPath(obj, path)
    },
  }
}

/** Register custom lambdas on a compiled expression */
function registerBindings(
  compiled: jsonata.Expression,
  bindings: Record<string, unknown>,
) {
  for (const [name, fn] of Object.entries(bindings)) {
    if (typeof fn === 'function') {
      compiled.registerFunction(name, fn as (...args: unknown[]) => unknown)
    }
  }
}

/**
 * Evaluate a JSONata expression over data.
 *
 * @param expr - JSONata expression string
 * @param data - Input data (any object)
 * @param fieldStore - Optional sandbox fieldStore for $field/$value bindings
 * @param extraBindings - Additional variables
 */
export async function evaluate(
  expr: string,
  data: unknown,
  fieldStore?: Map<string, FieldCell>,
  extraBindings?: Record<string, unknown>,
): Promise<unknown> {
  const compiled = compile(expr)
  const bindings = createBindings(fieldStore)

  registerBindings(compiled, bindings)
  if (extraBindings) {
    registerBindings(compiled, extraBindings)
  }

  return compiled.evaluate(data, extraBindings)
}

/**
 * Shorthand: evaluate expression and return as typed result.
 */
export async function query<T = unknown>(
  expr: string,
  data: unknown,
  fieldStore?: Map<string, FieldCell>,
): Promise<T> {
  return evaluate(expr, data, fieldStore) as Promise<T>
}

/**
 * Transform: evaluate expression, return both result and diff from original.
 */
export async function transform(
  expr: string,
  data: Record<string, unknown>,
  fieldStore?: Map<string, FieldCell>,
): Promise<{ result: unknown; patches: Array<{ path: string; value: unknown }> }> {
  const before = toFieldStore(data)
  const result = await evaluate(expr, data, fieldStore)

  const patches: Array<{ path: string; value: unknown }> = []
  if (result && typeof result === 'object' && !Array.isArray(result)) {
    const after = toFieldStore(result as Record<string, unknown>)
    for (const [path, entry] of Object.entries(after)) {
      const prev = before[path]
      if (!prev || prev[0] !== entry[0]) {
        patches.push({ path, value: entry[2] })
      }
    }
  }

  return { result, patches }
}
