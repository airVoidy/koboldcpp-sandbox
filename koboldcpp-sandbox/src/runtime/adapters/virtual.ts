/**
 * VirtualAdapter — the baseline adapter.
 *
 * No separate backend. Delegates everything to the Store (shared Data Layer).
 * This is the "lambda-on-resolve" case: object lives as raw FieldOps in Store;
 * projections compute views on access; signals bump on every change.
 *
 * Used as default for any object that doesn't declare a specific runtimeType.
 */
import type { Field, FieldOp, VirtualObject } from '@/data/types'
import type { Store } from '@/data/store'
import type { RuntimeAdapter } from '../types'

/**
 * Backend = just a { store, id } reference pair — no additional state.
 * The Store already holds the canonical FieldOps.
 */
export interface VirtualBackend {
  store: Store
  id: string
}

export function createVirtualAdapter(store: Store): RuntimeAdapter<VirtualBackend> {
  return {
    create(id, virtualType, initial, _config) {
      const writer = 'runtime'
      const existing = store.get(id)
      // Idempotent: if object already in Store (e.g. from ingest), no-op.
      // VirtualBackend holds no separate state — Store IS the state.
      if (!existing || existing.fields.size === 0) {
        // Seed _virtualType + initial fields as FieldOps
        store.apply(
          store.makeOp(writer, {
            objectId: id,
            fieldName: '_virtualType',
            op: 'set',
            type: 'value',
            content: virtualType,
          }),
        )
        for (const f of initial) {
          store.apply(
            store.makeOp(writer, {
              objectId: id,
              fieldName: f.name,
              op: 'set',
              type: f.type,
              content: f.content,
            }),
          )
        }
      }
      return { store, id }
    },

    read(backend): VirtualObject {
      const obj = backend.store.get(backend.id)
      if (obj) return obj
      // Object not in store — return an empty shell so consumers don't crash
      return {
        id: backend.id,
        virtualType: 'unknown',
        fields: new Map(),
        version: 0,
      }
    },

    apply(backend, op: FieldOp) {
      // Ensure op targets this backend's object (no cross-object writes from virtual)
      if (op.objectId !== backend.id) {
        throw new Error(
          `VirtualAdapter.apply: op targets ${op.objectId}, adapter owns ${backend.id}`,
        )
      }
      backend.store.apply(op)
    },

    subscribe(backend, cb) {
      return backend.store.subscribe(backend.id, cb)
    },

    serialize(backend): FieldOp[] {
      // All ops affecting this object
      return backend.store.allOps().filter((o) => o.objectId === backend.id)
    },

    hydrate(ops, _config) {
      if (ops.length === 0) throw new Error('VirtualAdapter.hydrate: no ops provided')
      const id = ops[0].objectId
      // Note: hydrate is a no-op in Store-shared model — ops should already be
      // applied to the Store. Caller is responsible for store.applyBatch(ops).
      // We just return the reference pair.
      // Here we retrieve the Store from a module singleton.
      throw new Error(
        'VirtualAdapter.hydrate: use store.applyBatch(ops) instead; adapter does not own Store',
      )
      // Unreachable; kept for interface conformance
      // return { store: <singleton>, id }
    },
  }
}

// Type guard
export function isVirtualBackend(x: unknown): x is VirtualBackend {
  return (
    typeof x === 'object' &&
    x !== null &&
    'store' in x &&
    'id' in x &&
    typeof (x as { id: unknown }).id === 'string'
  )
}
