import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import alias from '@rollup/plugin-alias'
import { fileURLToPath } from 'node:url'
import path from 'node:path'
import { createAtomSnapshotUnplugin } from './src/plugins/atom-snapshot'

const here = path.dirname(fileURLToPath(import.meta.url))

/**
 * Build / dev config notes:
 *
 * 1. Multi-module hub on one port — any external TS module can run as its own
 *    dev server on its own internal port; this Vite dev server forwards selected
 *    path prefixes to those targets via `server.proxy`. External users see ONE
 *    port (5177) regardless of how many modules are running behind the scenes.
 *
 *    Pattern:
 *      - internal module (Vue component under src/views/)  → route in router.ts
 *      - external module (separate dev server, any stack)   → proxy rule below
 *
 *    Landing page (HomeView.vue) lists both kinds; externals link to /proxy/<name>.
 *
 * 2. `atom-snapshot` plugin — unplugin factory for cross-bundler portability.
 *    Lives in `src/plugins/atom-snapshot.ts`. Demonstrates one-way projection
 *    from atom state → bundler virtual-module space.
 *
 * 3. `@rollup/plugin-alias` — canonical path aliases for atom imports.
 *    Demonstrates our "canonical-path-is-a-projection" axiom.
 */
export default defineConfig({
  plugins: [
    vue(),
    { ...alias({
      entries: [
        { find: '@atoms/registry', replacement: path.resolve(here, 'src/atom.ts') },
      ],
    }), enforce: 'pre' },
    createAtomSnapshotUnplugin().vite(),
  ],
  server: {
    port: 5177,
    headers: {
      'Cross-Origin-Opener-Policy': 'same-origin',
      'Cross-Origin-Embedder-Policy': 'require-corp',
    },
    /**
     * Proxy routes → external module dev servers.
     *
     * Vite's proxy is http-proxy-middleware under the hood. Supports ws: true,
     * rewrite(), configure(), target spec, and per-route overrides.
     *
     * Add a module:
     *   1. Start its dev server on its own port (examples: 5181, 5182, ...)
     *   2. Add a rule here that forwards /proxy/<name>/* → that server
     *   3. Add a ModuleEntry in src/router.ts with `external: '/proxy/<name>/'`
     *      so HomeView surfaces a link to it
     *
     * Rules are evaluated in order; first match wins. Use unique prefixes.
     */
    proxy: {
      // Example placeholder — replace target + uncomment when a module is live.
      // '/proxy/web-container': {
      //   target: 'http://localhost:5181',
      //   changeOrigin: true,
      //   ws: true,
      //   rewrite: (p) => p.replace(/^\/proxy\/web-container/, ''),
      // },
      // '/proxy/wasp-bootstrap': {
      //   target: 'http://localhost:5182',
      //   changeOrigin: true,
      //   ws: true,
      //   rewrite: (p) => p.replace(/^\/proxy\/wasp-bootstrap/, ''),
      // },
    },
  },
  preview: {
    headers: {
      'Cross-Origin-Opener-Policy': 'same-origin',
      'Cross-Origin-Embedder-Policy': 'require-corp',
    },
  },
  worker: {
    format: 'es',
  },
})
