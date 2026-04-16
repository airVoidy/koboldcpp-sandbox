/**
 * RuntimeLayer — dispatches ops to adapters by runtimeType.
 *
 * Sits above Data Layer Store. Each object registered with a RuntimeType;
 * ops routed to the matching adapter. Adapters hold library-specific backends;
 * RuntimeLayer only coordinates.
 *
 * Inheritance: `resolveRuntimeType(virtualType, schemas)` walks template chain
 * from schemas map to find the first declared `runtimeType`. Default = 'virtual'.
 */
import type { FieldOp, VirtualObject } from '@/data/types'
import type { Store } from '@/data/store'
import type {
  RuntimeAdapter,
  RuntimeObject,
  RuntimeType,
  RuntimeTemplateSchema,
} from './types'
import { createVirtualAdapter } from './adapters/virtual'

export class RuntimeLayer {
  private store: Store
  private adapters: Partial<Record<RuntimeType, RuntimeAdapter>> = {}
  private objects = new Map<string, RuntimeObject>()
  private schemas = new Map<string, RuntimeTemplateSchema>()

  constructor(store: Store) {
    this.store = store
    // Register VirtualAdapter by default
    this.registerAdapter('virtual', createVirtualAdapter(store))
  }

  /** Register an adapter implementation for a RuntimeType. */
  registerAdapter<B>(type: RuntimeType, adapter: RuntimeAdapter<B>): void {
    this.adapters[type] = adapter as RuntimeAdapter
  }

  /** Register a template schema (fed from /query on root/templates/...). */
  registerSchema(schema: RuntimeTemplateSchema): void {
    this.schemas.set(schema.type, schema)
  }

  /** Bulk register schemas. */
  registerSchemas(schemas: RuntimeTemplateSchema[]): void {
    for (const s of schemas) this.registerSchema(s)
  }

  /**
   * Walk template inheritance chain to find the effective runtimeType.
   * First declared type wins; default = 'virtual'.
   */
  resolveRuntimeType(virtualType: string): RuntimeType {
    let current: string | null | undefined = virtualType
    const visited = new Set<string>()
    while (current && !visited.has(current)) {
      visited.add(current)
      const schema = this.schemas.get(current)
      if (schema?.runtimeType) return schema.runtimeType
      current = schema?.inherits ?? null
    }
    return 'virtual'
  }

  /**
   * Resolve the effective config from template chain.
   * Deep-merges runtimeConfig up the inheritance chain (child overrides parent).
   */
  resolveConfig(virtualType: string): Record<string, unknown> {
    const chain: RuntimeTemplateSchema[] = []
    let current: string | null | undefined = virtualType
    const visited = new Set<string>()
    while (current && !visited.has(current)) {
      visited.add(current)
      const schema = this.schemas.get(current)
      if (schema) chain.unshift(schema)
      current = schema?.inherits ?? null
    }
    return chain.reduce(
      (acc, s) => ({ ...acc, ...(s.runtimeConfig ?? {}) }),
      {} as Record<string, unknown>,
    )
  }

  /**
   * Instantiate a RuntimeObject wrapper for an existing VirtualObject in Store.
   * Creates backend via the matching adapter.
   */
  instantiate(id: string, virtualType: string): RuntimeObject {
    const existing = this.objects.get(id)
    if (existing) return existing

    const runtimeType = this.resolveRuntimeType(virtualType)
    const adapter = this.requireAdapter(runtimeType)
    const config = this.resolveConfig(virtualType)

    // Seed with existing fields if any
    const existingObj = this.store.get(id)
    const initial = existingObj ? Array.from(existingObj.fields.values()) : []

    const backend = adapter.create(id, virtualType, initial, config)
    const schema = this.schemas.get(virtualType)

    const runtimeObj: RuntimeObject = {
      id,
      virtualType,
      runtimeType,
      backend,
      config,
      serializationProjection: schema?.serializationProjection,
      branch: schema?.branchPolicy?.auto
        ? {
            name: `${schema.branchPolicy.prefix ?? 'obj/'}${id}`,
            baseRef: 'main',
            divergedAt: this.store.cookie() as number,
            auto: true,
          }
        : undefined,
    }
    this.objects.set(id, runtimeObj)
    return runtimeObj
  }

  /** Apply an op — routed to the owning RuntimeObject's adapter. */
  applyOp(op: FieldOp): void {
    const runtimeObj = this.objects.get(op.objectId)
    if (!runtimeObj) {
      // Object not yet instantiated — apply directly to Store (virtual path)
      this.store.apply(op)
      return
    }
    const adapter = this.requireAdapter(runtimeObj.runtimeType)
    adapter.apply(runtimeObj.backend, op)
  }

  /** Read current VirtualObject view for an id. */
  readObject(id: string): VirtualObject | undefined {
    const runtimeObj = this.objects.get(id)
    if (runtimeObj) {
      const adapter = this.requireAdapter(runtimeObj.runtimeType)
      return adapter.read(runtimeObj.backend)
    }
    // Fallback: read directly from Store (virtual default)
    return this.store.get(id)
  }

  /** Subscribe to changes for an object (via its adapter). */
  subscribeObject(id: string, cb: () => void): () => void {
    const runtimeObj = this.objects.get(id)
    if (runtimeObj) {
      const adapter = this.requireAdapter(runtimeObj.runtimeType)
      return adapter.subscribe(runtimeObj.backend, cb)
    }
    return this.store.subscribe(id, cb)
  }

  /** Serialize an object's state as FieldOp[]. */
  serializeObject(id: string): FieldOp[] {
    const runtimeObj = this.objects.get(id)
    if (!runtimeObj) return []
    const adapter = this.requireAdapter(runtimeObj.runtimeType)
    return adapter.serialize(runtimeObj.backend)
  }

  /** Get the wrapper metadata for an object. */
  getObject(id: string): RuntimeObject | undefined {
    return this.objects.get(id)
  }

  /** List all registered RuntimeObjects. */
  allObjects(): RuntimeObject[] {
    return Array.from(this.objects.values())
  }

  /** Dispose all objects (cleanup workers/editors/etc). */
  dispose(): void {
    for (const ro of this.objects.values()) {
      const adapter = this.adapters[ro.runtimeType]
      adapter?.dispose?.(ro.backend)
    }
    this.objects.clear()
  }

  // ── Internals ──

  private requireAdapter(type: RuntimeType): RuntimeAdapter {
    const adapter = this.adapters[type]
    if (!adapter) {
      throw new Error(`No adapter registered for runtimeType: ${type}`)
    }
    return adapter
  }
}
