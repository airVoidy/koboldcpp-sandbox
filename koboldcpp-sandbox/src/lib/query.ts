/**
 * JSONata query/transform layer for client-side projections.
 *
 * Wraps jsonata as a generic exec op:
 * - input: runtime projection object
 * - expression: JSONata string
 * - bindings: custom variables ($field, $value, $children, $by_type)
 * - output: transformed data or patch-list
 *
 * Same jsonata-python on server, same jsonata npm on client.
 * One expression, two runtimes.
 */
import jsonata from 'jsonata'
import type { FieldEntry, Projection } from '@/types/runtime'
import { getByPath, toFieldStore, fromFieldStore } from '@/types/runtime'

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

/** Runtime lambda bindings — mirrors server-side registered functions */
function createBindings(projection?: Projection) {
  return {
    /** $field(path) — get field entry from flat store */
    field: (path: string): FieldEntry | undefined => {
      return projection?.flat_store[path]
    },

    /** $value(path) — get resolved value from flat store */
    value: (path: string): unknown => {
      const entry = projection?.flat_store[path]
      return entry ? entry[2] : undefined
    },

    /** $view(name) — get named view */
    view: (name: string): Record<string, FieldEntry> | undefined => {
      return projection?.views[name]
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
 * @param data - Input data (runtime projection, node, or any object)
 * @param projection - Optional projection for $field/$value/$view bindings
 * @param extraBindings - Additional variables available as $name in expression
 */
export async function evaluate(
  expr: string,
  data: unknown,
  projection?: Projection,
  extraBindings?: Record<string, unknown>,
): Promise<unknown> {
  const compiled = compile(expr)
  const bindings = createBindings(projection)

  // Register runtime lambdas
  registerBindings(compiled, bindings)

  // Register extra bindings as functions too
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
  projection?: Projection,
): Promise<T> {
  return evaluate(expr, data, projection) as Promise<T>
}

/**
 * Transform: evaluate expression, return both result and diff from original.
 * Useful for generating patch-lists from transform expressions.
 */
export async function transform(
  expr: string,
  data: Record<string, unknown>,
  projection?: Projection,
): Promise<{ result: unknown; patches: Array<{ path: string; value: unknown }> }> {
  const before = toFieldStore(data)
  const result = await evaluate(expr, data, projection)

  // If result is an object, diff it against original
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
