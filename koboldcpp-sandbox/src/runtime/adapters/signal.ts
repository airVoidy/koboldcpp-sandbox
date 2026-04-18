/**
 * SignalAdapter — local reactive state via signals micro-lib.
 *
 * Backend = { fields: Signal<Map<name, Field>>, version: Signal<number>, virtualType }.
 * No Store coupling — fully self-contained per object.
 *
 * Use case: high-frequency local updates (typing indicators, presence, ping counter).
 * Subscribe immediately emits on mutation; fast path for live UI.
 */
import type { Field, FieldOp, VirtualObject } from '@/data/types'
import { state, type Signal } from '@/data/signal'
import type { RuntimeAdapter } from '../types'

export interface SignalBackend {
  id: string
  virtualType: string
  fields: Signal<Map<string, Field>>
  version: Signal<number>
  opHistory: FieldOp[]         // kept for serialize/hydrate
}

export function createSignalAdapter(): RuntimeAdapter<SignalBackend> {
  return {
    create(id, virtualType, initial, _config) {
      const fields = new Map<string, Field>()
      for (const f of initial) fields.set(f.name, f)
      return {
        id,
        virtualType,
        fields: state(fields),
        version: state(0),
        opHistory: [],
      }
    },

    read(backend): VirtualObject {
      return {
        id: backend.id,
        virtualType: backend.virtualType,
        fields: backend.fields(),
        version: backend.version(),
      }
    },

    apply(backend, op: FieldOp) {
      if (op.objectId !== backend.id) {
        throw new Error(
          `SignalAdapter.apply: op targets ${op.objectId}, adapter owns ${backend.id}`,
        )
      }
      backend.opHistory.push(op)

      // Update virtualType if op targets it
      if (op.fieldName === '_virtualType' && op.op === 'set') {
        backend.virtualType = String(op.content ?? backend.virtualType)
      }

      // Update fields signal
      backend.fields.update((prev) => {
        const next = new Map(prev)
        if (op.op === 'unset') {
          next.delete(op.fieldName)
        } else if (op.op === 'set') {
          next.set(op.fieldName, {
            name: op.fieldName,
            type: op.type ?? 'value',
            content: op.content,
          })
        } else if (op.op === 'retype') {
          const existing = next.get(op.fieldName)
          if (existing && op.type) {
            next.set(op.fieldName, { ...existing, type: op.type })
          }
        }
        return next
      })
      backend.version.update((v) => v + 1)
    },

    subscribe(backend, cb) {
      // Subscribe to version signal — bumps on any mutation
      return backend.version.subscribe(cb)
    },

    serialize(backend): FieldOp[] {
      return [...backend.opHistory]
    },

    hydrate(ops, _config) {
      if (ops.length === 0) throw new Error('SignalAdapter.hydrate: no ops')
      const id = ops[0].objectId
      const fields = new Map<string, Field>()
      let virtualType = 'unknown'
      for (const op of ops) {
        if (op.objectId !== id) continue
        if (op.fieldName === '_virtualType' && op.op === 'set') {
          virtualType = String(op.content ?? 'unknown')
          continue
        }
        if (op.op === 'unset') {
          fields.delete(op.fieldName)
        } else if (op.op === 'set') {
          fields.set(op.fieldName, {
            name: op.fieldName,
            type: op.type ?? 'value',
            content: op.content,
          })
        } else if (op.op === 'retype') {
          const existing = fields.get(op.fieldName)
          if (existing && op.type) {
            fields.set(op.fieldName, { ...existing, type: op.type })
          }
        }
      }
      return {
        id,
        virtualType,
        fields: state(fields),
        version: state(ops.length),
        opHistory: [...ops],
      }
    },
  }
}
