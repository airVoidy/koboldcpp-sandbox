/**
 * VfsAdapter — file-addressable backend via just-bash.
 *
 * Backend = { bash: Bash, path: string, virtualType }.
 * Ops serialize as JSONL appended to `{path}.ops.jsonl`.
 * Current fields derived from `{path}.fields.json` snapshot (written on each apply).
 *
 * Use case: objects that need file semantics — baked snapshots, content that
 * other shell cmds operate on (cat/grep/jq), addressable FS paths for FS sync.
 *
 * Uses just-bash's InMemoryFs as the default VFS. For production, can swap
 * to OverlayFs over real FS, or MountableFs for multi-mount setups.
 * Security: DefenseInDepthBox available via just-bash for untrusted code.
 */
import type { Field, FieldOp, VirtualObject } from '@/data/types'
import type { RuntimeAdapter } from '../types'
import { Bash, InMemoryFs, type IFileSystem } from 'just-bash'

export interface VfsBackend {
  id: string
  virtualType: string
  bash: Bash
  basePath: string          // e.g., "/objects/msg_42"
  subscribers: Set<() => void>
}

export interface VfsConfig {
  /** Custom filesystem (InMemoryFs, OverlayFs, MountableFs, ReadWriteFs). */
  fs?: IFileSystem
  /** Base path prefix for objects (default "/objects"). */
  pathPrefix?: string
  /** Shared bash instance (lets multiple objects share one VFS). */
  bash?: Bash
}

// Singleton shared bash per config — many objects in one VFS
let _sharedBash: Bash | null = null

function getSharedBash(config?: VfsConfig): Bash {
  if (config?.bash) return config.bash
  if (!_sharedBash) {
    _sharedBash = new Bash({ fs: config?.fs ?? new InMemoryFs() })
  }
  return _sharedBash
}

export function createVfsAdapter(defaultConfig?: VfsConfig): RuntimeAdapter<VfsBackend> {
  return {
    create(id, virtualType, initial, config) {
      const merged = { ...defaultConfig, ...(config as VfsConfig) }
      const bash = getSharedBash(merged)
      const basePath = `${merged.pathPrefix ?? '/objects'}/${id.replace(/\//g, '_')}`
      const backend: VfsBackend = {
        id,
        virtualType,
        bash,
        basePath,
        subscribers: new Set(),
      }
      // Initialize VFS files
      void initBackend(backend, virtualType, initial)
      return backend
    },

    read(backend): VirtualObject {
      // Synchronous read from in-memory snapshot cache
      const cached = readCachedFields(backend)
      return {
        id: backend.id,
        virtualType: backend.virtualType,
        fields: cached.fields,
        version: cached.version,
      }
    },

    apply(backend, op: FieldOp) {
      if (op.objectId !== backend.id) {
        throw new Error(
          `VfsAdapter.apply: op targets ${op.objectId}, adapter owns ${backend.id}`,
        )
      }
      if (op.fieldName === '_virtualType' && op.op === 'set') {
        backend.virtualType = String(op.content ?? backend.virtualType)
      }
      // Append op to JSONL + update field snapshot
      void appendOp(backend, op)
      backend.subscribers.forEach((cb) => cb())
    },

    subscribe(backend, cb) {
      backend.subscribers.add(cb)
      return () => backend.subscribers.delete(cb)
    },

    serialize(backend): FieldOp[] {
      return readCachedOps(backend)
    },

    hydrate(ops, config) {
      if (ops.length === 0) throw new Error('VfsAdapter.hydrate: no ops')
      const id = ops[0].objectId
      const merged = { ...defaultConfig, ...(config as VfsConfig) }
      const bash = getSharedBash(merged)
      const basePath = `${merged.pathPrefix ?? '/objects'}/${id.replace(/\//g, '_')}`
      const backend: VfsBackend = {
        id,
        virtualType: 'unknown',
        bash,
        basePath,
        subscribers: new Set(),
      }
      void replayOps(backend, ops)
      return backend
    },

    dispose(backend) {
      backend.subscribers.clear()
    },
  }
}

// ── Internal VFS helpers ──

/**
 * Per-backend in-memory cache. just-bash filesystem ops are async but our
 * adapter interface is synchronous (for signal/subscription model). We write
 * through to VFS async, but keep a sync cache for read().
 */
interface BackendCache {
  fields: Map<string, Field>
  version: number
  ops: FieldOp[]
}

const caches = new WeakMap<VfsBackend, BackendCache>()

function getCache(backend: VfsBackend): BackendCache {
  let c = caches.get(backend)
  if (!c) {
    c = { fields: new Map(), version: 0, ops: [] }
    caches.set(backend, c)
  }
  return c
}

async function initBackend(
  backend: VfsBackend,
  virtualType: string,
  initial: Field[],
): Promise<void> {
  const { bash, basePath } = backend
  // Ensure directory exists
  await bash.exec(`mkdir -p "${basePath}"`)
  // Seed metadata file
  const meta = { id: backend.id, virtualType, created: new Date().toISOString() }
  await bash.exec(
    `cat > "${basePath}/meta.json" <<EOF\n${JSON.stringify(meta)}\nEOF`,
  )
  // Seed initial fields
  const cache = getCache(backend)
  for (const f of initial) {
    cache.fields.set(f.name, f)
  }
  await writeFieldsSnapshot(backend)
}

async function appendOp(backend: VfsBackend, op: FieldOp): Promise<void> {
  const cache = getCache(backend)
  cache.ops.push(op)
  // Update in-memory fields
  if (op.op === 'unset') {
    cache.fields.delete(op.fieldName)
  } else if (op.op === 'set') {
    cache.fields.set(op.fieldName, {
      name: op.fieldName,
      type: op.type ?? 'value',
      content: op.content,
    })
  } else if (op.op === 'retype') {
    const existing = cache.fields.get(op.fieldName)
    if (existing && op.type) {
      cache.fields.set(op.fieldName, { ...existing, type: op.type })
    }
  }
  cache.version++
  // Append op line to VFS
  const line = JSON.stringify(op)
  // Use printf for safe embedding
  await backend.bash.exec(
    `printf '%s\\n' ${JSON.stringify(line)} >> "${backend.basePath}/ops.jsonl"`,
  )
  await writeFieldsSnapshot(backend)
}

async function writeFieldsSnapshot(backend: VfsBackend): Promise<void> {
  const cache = getCache(backend)
  const snapshot = {
    id: backend.id,
    virtualType: backend.virtualType,
    version: cache.version,
    fields: Object.fromEntries(
      Array.from(cache.fields.entries()).map(([k, v]) => [k, v]),
    ),
  }
  await backend.bash.exec(
    `cat > "${backend.basePath}/fields.json" <<EOF\n${JSON.stringify(snapshot)}\nEOF`,
  )
}

function readCachedFields(backend: VfsBackend): {
  fields: Map<string, Field>
  version: number
} {
  const cache = getCache(backend)
  return { fields: cache.fields, version: cache.version }
}

function readCachedOps(backend: VfsBackend): FieldOp[] {
  return [...getCache(backend).ops]
}

async function replayOps(backend: VfsBackend, ops: FieldOp[]): Promise<void> {
  await backend.bash.exec(`mkdir -p "${backend.basePath}"`)
  for (const op of ops) {
    await appendOp(backend, op)
  }
}
