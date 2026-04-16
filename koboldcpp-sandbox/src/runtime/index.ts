/**
 * Runtime Object Layer — entry point + singleton.
 */
import { RuntimeLayer } from './layer'
import { getStore } from '@/data'

export * from './types'
export { RuntimeLayer } from './layer'
export { createVirtualAdapter } from './adapters/virtual'

let _runtime: RuntimeLayer | null = null

export function getRuntime(): RuntimeLayer {
  if (!_runtime) {
    _runtime = new RuntimeLayer(getStore())
    if (typeof window !== 'undefined') {
      ;(window as unknown as { __runtime: RuntimeLayer }).__runtime = _runtime
    }
  }
  return _runtime
}

/**
 * Instantiate RuntimeObjects for all VirtualObjects currently in Store.
 * Call after ingesting server state so every object has an adapter backend.
 */
export function instantiateAllFromStore(): void {
  const runtime = getRuntime()
  const store = getStore()
  for (const obj of store.all()) {
    runtime.instantiate(obj.id, obj.virtualType)
  }
}
