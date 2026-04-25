import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'

/**
 * Central module registry — every TS module reachable on this dev server (5177).
 *
 * Two kinds of modules:
 *
 *   1. **Internal** — Vue view living under src/views/. Added as a route record
 *      below. Shares the build + deps with the hub.
 *
 *   2. **External** — separate project with its own dev server. Proxied through
 *      `server.proxy` in vite.config.ts. User sees one port; internally each
 *      module runs on its own port.
 *
 * Adding a new module:
 *   - internal:
 *       a) create src/views/<Name>View.vue
 *       b) add route record below
 *       c) append ModuleEntry (without `external`)
 *   - external:
 *       a) run the module's own dev server on a free port
 *       b) add proxy rule in vite.config.ts: '/proxy/<name>' → target
 *       c) append ModuleEntry with `external: '/proxy/<name>/'`
 *
 * Either way, HomeView.vue surfaces a card automatically.
 */

export interface ModuleEntry {
  name: string
  title: string
  description: string
  tags?: string[]
  /**
   * If present, this is a proxied external module. Clicking navigates the
   * browser to this path (outside Vue Router), which the dev server proxies
   * to an external target. Leave blank for internal (router-resolved) modules.
   */
  external?: string
  /** Route path for internal modules. Ignored if `external` is set. */
  path?: string
}

export const moduleEntries: ModuleEntry[] = [
  {
    name: 'atom-demo',
    path: '/atom-demo',
    title: 'Atom + Lexical Demo',
    description:
      'Universal Atom primitive, AtomRegistry, wrapper layer (logging/timing/caching), Lexical text canvas, Vite virtual-module projection.',
    tags: ['atom', 'lexical', 'wrapper', 'virtual-module'],
  },
  {
    name: 'workbench',
    path: '/workbench',
    title: 'Workbench',
    description:
      'All modules running simultaneously as floating iframe windows on one page. Drag headers to move, drag corners to resize, click to bring to front.',
    tags: ['workbench', 'floating', 'multi-module'],
  },
  {
    name: 'wrappers-demo',
    path: '/wrappers-demo',
    title: 'Cross-Type Wrappers',
    description:
      'Atom wrappers bridging different container types. ContainerSpec outputs auto-mount as live Vue components (Lexical / LangExtract / web-container stub). Bridge wrappers transform one type into another (e.g. bash stdout → Lexical view).',
    tags: ['wrapper', 'cross-type', 'mount', 'containers'],
  },
  {
    name: 'atomic-list',
    path: '/atomic-list',
    title: 'AtomicList — Array vs Nested',
    description:
      'Two variants of atom collections: positional array, and hash-keyed nested form ("schema | value"). Side-by-side playground showing structural dedup on the nested side.',
    tags: ['atomic-list', 'collection', 'hash'],
  },
  {
    name: 'namescope',
    path: '/namescope',
    title: 'Local Namescope',
    description:
      'Two-detached-list pattern for name aliasing without polluting the global namespace. Left = cells (isolated consumers with personal alias spaces); right = namescope container (virtual type catalog + shared aliases). One-way: cells → scope.',
    tags: ['namescope', 'aliases', 'two-list', 'scope'],
  },
  {
    name: 'extractors',
    path: '/extractors',
    title: 'Extractors — named projections',
    description:
      'Catalog of named extractors (CSV / JSON / Markdown / SQL-Insert / Python DF / Pretty / Jupyter .ipynb) and aggregators (COUNT / SUM / AVG) surfaced via right-click context menu. Plus per-row "Copy as..." identity projections (incl. MIME bundle a la Jupyter).',
    tags: ['extractor', 'projection', 'catalog', 'jupyter', 'mime'],
  },
  {
    name: 'canvas-notebook',
    path: '/canvas-notebook',
    title: 'Canvas Notebook',
    description:
      'Jupyter-compatible .ipynb with 2D-positioned cells. Position stored as text in cell.metadata.atom.pos — standard Jupyter ignores, renders linear. Our viewer renders as draggable free-positioned cards with overlaps.',
    tags: ['jupyter', 'ipynb', 'canvas', 'cells', 'roundtrip'],
  },
  {
    name: 'langextract',
    path: '/langextract',
    title: 'LangExtract — atomic / list / LangScope',
    description:
      'Spans wrapped as atoms, grouped into detached per-class NestedAtomicLists, namescope registering each span + first:<class> aliases, hierarchical LangScope nesting (LangChain-style parent chain with lookupAlias walking up).',
    tags: ['langextract', 'shadow', 'atomic', 'langscope', 'hierarchical'],
  },
  {
    name: 'aabb-layout',
    path: '/aabb-layout',
    title: 'Aabb Layout — three-zone list',
    description:
      'Three buckets per list: past (-1), current (0), future (+1). Move items freely between zones; checkpoint promotes +1 → 0; archive demotes 0 → -1. Zones are mutable buckets, not strict notation.',
    tags: ['aabb', 'layout', 'cleanroom', 'three-zone'],
  },
  {
    name: 'slot-inspector',
    path: '/slot-inspector',
    title: 'ProjectionSlot ↔ Lexical bridge',
    description:
      'Pipeline lifecycle made visible: declared → resolving → materialized | shadow | problem. Each transition is appended as a paragraph in a Lexical editor — the editor itself IS the computation log surface.',
    tags: ['projection-slot', 'pipeline', 'lexical', 'cleanroom'],
  },
  {
    name: 'composition-demo',
    path: '/composition-demo',
    title: 'Composition — Gateway + Pipeline + AABB',
    description:
      'Three cleanroom primitives composing without mutual coupling. Gateway routes payloads by content; pipeline materializes each as its own slot; on-resolve hook routes the materialized slot into the AABB zone the gateway picked.',
    tags: ['gateway', 'pipeline', 'aabb', 'composition', 'cleanroom'],
  },
  // Example external module (uncomment + configure proxy in vite.config.ts):
  // {
  //   name: 'web-container',
  //   external: '/proxy/web-container/',
  //   title: 'Web Container (external)',
  //   description: 'Browser-side bash + compile sandbox. Runs as its own dev server, proxied here.',
  //   tags: ['shell', 'compile', 'external'],
  // },
]

const routes: RouteRecordRaw[] = [
  {
    path: '/',
    name: 'home',
    component: () => import('./views/HomeView.vue'),
  },
  {
    path: '/atom-demo',
    name: 'atom-demo',
    component: () => import('./views/AtomDemoView.vue'),
  },
  {
    path: '/workbench',
    name: 'workbench',
    component: () => import('./views/WorkbenchView.vue'),
  },
  {
    path: '/wrappers-demo',
    name: 'wrappers-demo',
    component: () => import('./views/WrappersDemoView.vue'),
  },
  {
    path: '/atomic-list',
    name: 'atomic-list',
    component: () => import('./views/AtomicListView.vue'),
  },
  {
    path: '/namescope',
    name: 'namescope',
    component: () => import('./views/NamescopeView.vue'),
  },
  {
    path: '/extractors',
    name: 'extractors',
    component: () => import('./views/ExtractorsView.vue'),
  },
  {
    path: '/canvas-notebook',
    name: 'canvas-notebook',
    component: () => import('./views/CanvasNotebookView.vue'),
  },
  {
    path: '/langextract',
    name: 'langextract',
    component: () => import('./views/LangExtractView.vue'),
  },
  {
    path: '/aabb-layout',
    name: 'aabb-layout',
    component: () => import('./views/AabbLayoutView.vue'),
  },
  {
    path: '/slot-inspector',
    name: 'slot-inspector',
    component: () => import('./views/SlotInspectorView.vue'),
  },
  {
    path: '/composition-demo',
    name: 'composition-demo',
    component: () => import('./views/CompositionDemoView.vue'),
  },
]

export const router = createRouter({
  history: createWebHistory(),
  routes,
})
