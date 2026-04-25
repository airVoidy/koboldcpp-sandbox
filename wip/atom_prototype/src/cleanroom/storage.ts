// Storage backends for snapshot persistence.
//
// `StorageBackend` is the abstract surface — put / get / list keyed entries.
// `MemoryStorageBackend` works in Node + browser, used in tests.
// `OpfsStorageBackend` works only in browsers with OPFS (guarded by feature
// detection), persists across page reloads under the origin-private root.
//
// Both implementations carry only `JsonValue` — no binary streams, no schemas.
// That keeps the interface usable with AtomicSnapshot directly.

import type { JsonValue } from './store'

export interface StorageBackend {
  put(key: string, value: JsonValue): Promise<void>
  get(key: string): Promise<JsonValue | undefined>
  list(prefix?: string): Promise<string[]>
  delete(key: string): Promise<void>
}

/**
 * MemoryStorageBackend: trivial Map-backed storage. Lives only in process
 * memory; useful for tests and short-lived sessions.
 */
export class MemoryStorageBackend implements StorageBackend {
  private readonly entries = new Map<string, JsonValue>()

  async put(key: string, value: JsonValue): Promise<void> {
    this.entries.set(key, value)
  }

  async get(key: string): Promise<JsonValue | undefined> {
    return this.entries.get(key)
  }

  async list(prefix?: string): Promise<string[]> {
    const keys = [...this.entries.keys()]
    if (!prefix) return keys
    return keys.filter((k) => k.startsWith(prefix))
  }

  async delete(key: string): Promise<void> {
    this.entries.delete(key)
  }

  /** Test/debug accessor: number of entries currently held. */
  size(): number {
    return this.entries.size
  }
}

/**
 * Detect whether OPFS is available in the current environment.
 * Returns true only in browsers with `navigator.storage.getDirectory`.
 */
export function isOpfsAvailable(): boolean {
  if (typeof globalThis === 'undefined') return false
  const nav = (globalThis as { navigator?: unknown }).navigator
  if (!nav || typeof nav !== 'object') return false
  const storage = (nav as { storage?: unknown }).storage
  if (!storage || typeof storage !== 'object') return false
  const getDirectory = (storage as { getDirectory?: unknown }).getDirectory
  return typeof getDirectory === 'function'
}

/**
 * OpfsStorageBackend: persists JsonValue entries as files under an origin-
 * private directory. Browser-only — throws synchronously on construction
 * if OPFS isn't available.
 *
 * Each entry becomes one file: `<rootDir>/<encodedKey>.json`. Keys are
 * percent-encoded for filesystem safety.
 */
export class OpfsStorageBackend implements StorageBackend {
  private rootHandlePromise: Promise<FileSystemDirectoryHandle> | null = null

  constructor(private readonly rootName: string = 'atomic-cleanroom') {
    if (!isOpfsAvailable()) {
      throw new Error('OPFS not available in this environment')
    }
  }

  private async rootHandle(): Promise<FileSystemDirectoryHandle> {
    if (!this.rootHandlePromise) {
      this.rootHandlePromise = (async () => {
        const navStorage = (globalThis as unknown as {
          navigator: { storage: { getDirectory: () => Promise<FileSystemDirectoryHandle> } }
        }).navigator.storage
        const root = await navStorage.getDirectory()
        return root.getDirectoryHandle(this.rootName, { create: true })
      })()
    }
    return this.rootHandlePromise
  }

  private fileName(key: string): string {
    return `${encodeURIComponent(key)}.json`
  }

  async put(key: string, value: JsonValue): Promise<void> {
    const root = await this.rootHandle()
    const file = await root.getFileHandle(this.fileName(key), { create: true })
    const writable = await file.createWritable()
    await writable.write(JSON.stringify(value))
    await writable.close()
  }

  async get(key: string): Promise<JsonValue | undefined> {
    const root = await this.rootHandle()
    try {
      const handle = await root.getFileHandle(this.fileName(key), { create: false })
      const file = await handle.getFile()
      const text = await file.text()
      return JSON.parse(text) as JsonValue
    } catch {
      return undefined
    }
  }

  async list(prefix?: string): Promise<string[]> {
    const root = await this.rootHandle()
    const keys: string[] = []
    // FileSystemDirectoryHandle is async-iterable (entries()).
    const iterable = root as unknown as {
      entries: () => AsyncIterable<[string, FileSystemHandle]>
    }
    for await (const [name] of iterable.entries()) {
      if (!name.endsWith('.json')) continue
      const key = decodeURIComponent(name.slice(0, -'.json'.length))
      if (!prefix || key.startsWith(prefix)) {
        keys.push(key)
      }
    }
    return keys
  }

  async delete(key: string): Promise<void> {
    const root = await this.rootHandle()
    try {
      await root.removeEntry(this.fileName(key))
    } catch {
      // ignore missing entries
    }
  }
}
