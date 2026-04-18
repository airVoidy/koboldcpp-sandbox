import { createUnplugin } from 'unplugin'

/**
 * Atom snapshot plugin — built via unplugin for cross-bundler portability.
 *
 * Same factory produces plugins for Vite, Rollup, Webpack, Rspack, and esbuild.
 * The factory itself knows nothing about a specific bundler — it speaks
 * unplugin's common plugin interface (resolveId / load / transform / ...).
 *
 * Architectural framing:
 *   - This is a **one-way projection** from our atom-registry state into
 *     bundler virtual-module space. The atom state stays authoritative;
 *     the virtual module is a generated snapshot.
 *   - Our Virtual Objects are pure assembly primitives (runtime-operational);
 *     Vite/Rollup/unplugin virtual modules are build/dev-time module-space
 *     artifacts. Related by shared `name → generated payload` shape, but
 *     different scopes.
 *   - `unplugin` matches our "wire format stable across hosts" principle
 *     applied to plugins: write the projection once, host it anywhere.
 *
 * Usage pattern:
 *   - `import snapshot from 'virtual:atom-snapshot'` in app code
 *   - Plugin intercepts the import, synthesizes module content at load time
 *   - Content is a JSON snapshot of the atom-registry state
 *   - In a real runtime we'd wire this to the actual AtomRegistry;
 *     here it's a static stand-in so the projection mechanism is visible.
 */
const VIRTUAL_ID = 'virtual:atom-snapshot'
const RESOLVED = '\0' + VIRTUAL_ID

export interface AtomSnapshotOptions {
  /**
   * If set, overrides the default static snapshot with a custom getter.
   * In a real integration this would read from the live AtomRegistry.
   */
  getSnapshot?: () => { generatedAt: number; atomIds: string[]; values: Record<string, unknown> }
}

export function createAtomSnapshotUnplugin(options: AtomSnapshotOptions = {}) {
  const { getSnapshot } = options

  return createUnplugin(() => ({
    name: 'atom-snapshot',
    resolveId(id) {
      if (id === VIRTUAL_ID) return RESOLVED
    },
    loadInclude(id) {
      return id === RESOLVED
    },
    load() {
      const snapshot = getSnapshot
        ? getSnapshot()
        : {
            generatedAt: Date.now(),
            atomIds: ['insert-text', 'clear-editor', 'len-projection'],
            values: {
              'demo:flag': true,
              'demo:count': 0,
            },
          }
      return `export default ${JSON.stringify(snapshot, null, 2)}`
    },
  }))
}
