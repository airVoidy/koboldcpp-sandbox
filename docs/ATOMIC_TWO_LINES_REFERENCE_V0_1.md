# Atomic — Two Existing Lines, Reference for a New Parallel Project v0.1

## Purpose

Complete reference of the two independent atomic-ish implementations currently living in the repo. Written as **starter material for a fresh parallel project** that:

- starts from scratch (no code inherited)
- uses both existing lines as design references
- takes `Atom` as the unifying primitive (per §Divergences — the term means different things today)
- treats unifying the two lines as the first worked example

The two lines:

| Line | Path | Stack | Entry port | Flavor |
|------|------|-------|------------|--------|
| **atom_prototype** | `wip/atom_prototype/` | Vue 3 + rolldown-Vite 5 + Lexical core | `:5177` | debug lab, many modules, hash-first identity, type catalog |
| **koboldcpp-sandbox** | `koboldcpp-sandbox/` | React 19 + Vite 6 + Tailwind 4 + Radix + @tanstack/react-query | `:5173` | production-leaning chat runtime, FieldOp log, adapter-polymorphic |

Each is self-contained. They share **zero code**. They share **several invariants** (§ Shared Invariants). The terminology *overlaps but means different things* (§ Term Collisions).

---

## Part I — `wip/atom_prototype/` — full inventory

### Stack

```
Vue 3.5 (Composition API)              — reactivity: ref / shallowRef / computed / watch
rolldown-Vite 5.4                      — Rust bundler (beta binding for win32)
Lexical 0.43 core (no @lexical/react)  — mount via createEditor + setRootElement
@lexical/{rich-text, history}          — rich text + undo/redo registrations
vue-router 4                           — per-view routes
synckit                                — installed, stubbed in workers/resolver.worker.ts
unplugin                               — for the atom-snapshot virtual module plugin
vitest + vue-tsc                       — 109 tests, strict TS
```

### Source tree

```
src/
├── atom.ts              ←────────────────── compute primitive (operation + wrappers)
├── atomic-list.ts       ←────────────────── collection primitive (array + nested)
├── namescope.ts         ←────────────────── wrapper + registry + relative names
├── mount.ts             ←────────────────── ContainerSpec → live Vue component
├── extractors.ts        ←────────────────── named-projection catalog (IntelliJ-DB pattern)
├── canvas-notebook.ts   ←────────────────── Jupyter .ipynb round-trip with 2D positioning
├── canvas-widgets.ts    ←────────────────── table/filter/aggregator widgets
├── langextract.ts       ←────────────────── shadow-layer wrap of langextract format
├── plugins/
│   └── atom-snapshot.ts                ─── unplugin factory: atom state → Vite virtual module
├── workers/
│   └── resolver.worker.ts              ─── synckit stub (not yet wired)
├── router.ts                           ─── central route + ModuleEntry registry
├── main.ts / App.vue                   ─── entry, shell
├── components/
│   ├── EditorHost.vue                  ─── Lexical mount point
│   ├── AtomDemo.vue / VirtualObjectDemo.vue
│   ├── containers/
│   │   ├── LexicalContainer.vue
│   │   ├── LangExtractStub.vue
│   │   └── WebContainerStub.vue
│   └── widgets/
│       ├── TableWidget.vue
│       ├── FilterWidget.vue
│       └── AggregatorWidget.vue
└── views/
    ├── HomeView.vue                        (module hub, reads moduleEntries)
    ├── AtomDemoView.vue                    → atom.ts + Lexical
    ├── WorkbenchView.vue                   (all modules as floating iframes)
    ├── WrappersDemoView.vue                → atom + mount + containers
    ├── AtomicListView.vue                  → atomic-list standalone
    ├── NamescopeView.vue                   → namescope standalone
    ├── ExtractorsView.vue                  → extractors + mock rows
    ├── CanvasNotebookView.vue              → canvas-notebook + widgets
    └── LangExtractView.vue                 → langextract + atom + namescope
```

### Primitive summary (what each module exports)

#### `atom.ts` — **compute atom** (op unit)

```ts
type AtomKind = 'container' | 'op' | 'projection' | 'shadow' | 'group'
type OpSpec =
  | { type: 'noop' }
  | { type: 'lambda'; fn: (input: unknown) => unknown | Promise<unknown> }
  | { type: 'named'; name: string; args?: unknown }   // not wired

interface Atom {
  id: string
  ref?: AtomRef
  kind: AtomKind
  inScope: AtomRef[]
  op?: OpSpec
  outScope: AtomRef[]
  payload?: unknown
  tags: string[]
  wrappers: string[]
}

class AtomRegistry {
  register(atom); registerWrapper(wrapper); setValue(ref, v); getValue(ref)
  onRun(logger); run(atomId) → output
}

// pre-baked wrappers: logging, timing, caching — Express-middleware style
```

Role: **operation graph node**. One atom = one step. Wrappers decorate around execution without changing identity. `inScope`/`outScope` refer to atom refs; `run()` resolves inputs, applies op under wrapper chain, writes output to all outScope refs, emits AtomRunResult.

#### `atomic-list.ts` — **universal collection**

```ts
interface AtomicListBase<T> {
  kind: 'array' | 'nested'
  size; items(); keys(); entries(); get; has; add; remove; clear; toJSON
}
class ArrayAtomicList<T>    // keys = integer positions
class NestedAtomicList<T>   // keys = content-hash `<schema>|<value>`, dedup-aware

computeAtomicHash(value, fieldValueType?) → { schemaPart, valuePart, full }
deriveSchema(value) → { relFields, localType }  // one-level shape inference
```

Role: **collection primitive for any element type**. `T = unknown` by convention → objects, scalars, lists mix freely. Nested variant dedups by structural equality via human-readable hash.

#### `namescope.ts` — **wrapper + registry + relative names**

```ts
interface VirtualTypeEntry {
  hash: Hash
  type: string
  payload: unknown
  tags?: string[]
}

class Namescope {
  registerType(entry); has; get; entries; size
  filter; sort; pick                               // query ops
  setSharedAlias(name, hash); setPersonalAlias(cellId, name, hash)
  resolve(name, cellId?) → Hash | undefined        // personal-first, falls back to shared
}

class NamescopeCell {
  id: string; resolve(name); deref(name)           // personal aliases scoped to cell
}
```

Role:
- **Universal wrapper** — `VirtualTypeEntry` is the canonical form (any object wraps into `{hash, type, payload, tags}`).
- **Type catalog** — `Namescope.types: Map<Hash, VirtualTypeEntry>`.
- **Relative names** — two-detached-list pattern: cells (left) resolve names through scope (right), scope doesn't track cells, personal > shared > undefined.

#### `mount.ts` — **cross-type bridge + auto-mount**

```ts
interface ContainerSpec { type; id; title; props }         // parallel to VirtualTypeEntry
registerContainer(type, component, label)
mountManager — holds `mounted: Mounted[]` reactive array
autoMountWrapper(id)                                       // atom output with ContainerSpec → mount
bridgeWrapper(id, targetAtom, transform)                   // transform cross-type
```

Role: bridge compute-atom output (`ContainerSpec`) to live Vue component instance (`Mounted` in floating cell).

#### `extractors.ts` — **named projection catalog**

```ts
interface Extractor {
  id; label; category: 'extractor' | 'aggregator' | 'schema' | 'layout'
  format; description?; run(rows: Row[]) → string
}
registerExtractor; getExtractor; listExtractors(category?); runExtractor(id, rows)

// Built-ins: csv, json, md, sql-insert, python-df, pretty, ipynb,
// aggregators: count, sum, avg
// Identity projections: json-single, csv-line, key-value, sql-single, primary-key,
//                        atom-uri, row-index, mime-bundle
```

Role: named pure projections (IntelliJ-DB inspired catalog, IPython `_repr_mimebundle_`-compatible). Same data → N representations, user picks at read time.

#### `canvas-notebook.ts` — **Jupyter .ipynb with 2D positions**

```ts
type JCellType = 'markdown' | 'code' | 'raw'
interface CanvasCell {
  id; cell_type; source; pos: {x,y}; size: {w,h}; z
  faces?: Record<string, {content: string}>      // shadow projections (mutable)
  activeFace?: string
  metadata: {atom: {pos, size, z, faces, activeFace, widget}, ...}
  outputs?; execution_count?
}
loadCanvasCells(jupyterNotebook)
saveCanvasCells(cells) → JupyterNotebook
seedCells()
newCell(type, x, y, z)
```

Role: Jupyter-format interchange with our canvas-specific extensions in `cell.metadata.atom.*`. Standard Jupyter readers ignore extensions, render linear; our viewer reads them as 2D positions + multi-face sides.

#### `langextract.ts` — **shadow-layer wrap of annotated text**

```ts
interface LangExtractSpan { extraction_class; extraction_text; char_interval; attributes? }
interface AnnotatedDocument { document_id; text; extractions: LangExtractSpan[] }

atomic(span, docId?) → Atom                       // span → compute atom (pure projection)
groupByClass(doc) → Record<class, NestedAtomicList<Span>>
toAtomicList(doc) → NestedAtomicList<Span>

class LangScope {
  id; doc; lists; namescope; metadata; parent?
  childScope(id, doc, metadata?); chain(); lookupAlias(name)  // walks parent chain
}
spanProjections: { text, range, klass, attrs, withContext, uri }
```

Role:
- `atomic(span)` produces a compute atom whose op is a pure projection returning span payload
- `groupByClass` builds detached per-class NestedAtomicLists
- `LangScope` nests hierarchically; `lookupAlias` walks parent chain (LangChain-style)
- **this is the most fully-integrated view** — namescope + atomic-list + atom + aliases + projection chain all working together

### Internal dependency graph

```
          atom.ts
             ▲
             │ imports
             │
        ┌────┴─────┬──────────┐
        │          │          │
   extractors.ts  mount.ts  langextract.ts
                                  │
                                  ▼ imports
                            atomic-list.ts ←── computeAtomicHash used for hash
                                  │                identity in langextract
                                  │
                                  ▼ imports (langextract only)
                             namescope.ts
                                  ▲
                                  │ standalone (NamescopeView)
                                  │
                             canvas-notebook.ts  (standalone, imports nothing from above)
                             canvas-widgets.ts   (used by canvas-notebook)
```

**Which view uses what**:

| View | Uses |
|------|------|
| AtomDemoView | atom, Lexical core, wrappers |
| WrappersDemoView | atom, mount, container components |
| AtomicListView | atomic-list |
| NamescopeView | namescope |
| ExtractorsView | extractors, mock rows |
| CanvasNotebookView | canvas-notebook, canvas-widgets |
| LangExtractView | langextract (→ atom, atomic-list, namescope) |
| WorkbenchView | iframes into all other views |

**Shared code between modules** — quite little:
- `langextract.ts` is the only module importing all three (atom + atomic-list + namescope)
- `mount.ts` + `extractors.ts` only import `atom`
- `canvas-notebook.ts` is isolated
- `atomic-list`, `namescope`, `atom` are independent primitives

---

## Part II — `koboldcpp-sandbox/` — full inventory

### Stack

```
React 19.2                             — functional components, hooks, useSyncExternalStore
Vite 6.4                               — bundler, proxy /api/* → Python server :5002
Tailwind 4 + @tailwindcss/vite         — utility CSS
Radix UI (dialog, dropdown, scroll-area, slot, tabs, tooltip)
@tanstack/react-query 5                — async data fetching
@xterm/xterm 6 + addon-fit + web-links — real terminal UI
just-bash 2.14                         — POSIX shell in browser, InMemoryFs
ahooks 3                               — React hooks toolkit
jsonata 2                              — JSON query
cmdk                                   — command palette
lexical 0.43 + @lexical/{rich-text, history, utils, selection}
lucide-react                           — icon set
react-resizable-panels
vite-plugin-node-polyfills             — zlib/buffer/util for browser
eslint 9 + typescript-eslint + react-hooks plugin
```

No Vue, no vitest (no test infra yet), no Vitest. Has eslint. Uses SWC for React (`@vitejs/plugin-react-swc`).

### Source tree

```
src/
├── App.tsx                    — root, hash-based routing (#runtime-demo + default)
├── App.css / index.css
├── main.tsx                   — entry, mounts <App/>
├── data/                      ←────── truth layer
│   ├── types.ts                       FieldOp, Field, VirtualObject, ProjectionSpec,
│   │                                  VirtualList (helper only), Cookie
│   ├── signal.ts                      ~100 LOC signal micro-lib: state/computed/
│   │                                  effect/event with auto-tracked deps
│   ├── store.ts                       Store: op log + registry + per-object version
│   │                                  signal + projection registry + JSONL serialize
│   │                                  (Langextract-compatible)
│   ├── lazy.ts                        collectMissingRefs, resolveMissing,
│   │                                  ingestQueryNode ("virtual object as
│   │                                  self-describing query")
│   └── index.ts                       getStore() singleton, ingestChatState,
│                                      window.__store
│
├── runtime/                   ←────── adapter-polymorphic runtime layer
│   ├── types.ts                       RuntimeType union, RuntimeObject,
│   │                                  RuntimeAdapter<B>, BranchMeta,
│   │                                  RuntimeTemplateSchema
│   ├── layer.ts                       RuntimeLayer: adapter router +
│   │                                  inheritance walker + instantiation +
│   │                                  subscribe fan-out
│   ├── middlelayer.ts                 Middlelayer: before/after hooks, prev/new
│   │                                  state snapshots, _exec.<callId>.* shadow
│   │                                  metadata, call log
│   ├── adapters/
│   │   ├── virtual.ts                 delegates to Store (baseline)
│   │   ├── signal.ts                  in-memory reactive backend
│   │   └── vfs.ts                     file-backed via just-bash InMemoryFs
│   └── index.ts                       getRuntime(), registers adapters,
│                                      window.__runtime + window.__middlelayer
│
├── hooks/
│   ├── useStore.ts                    useStore, useVirtualObject(id),
│   │                                  useProjection(id, name), useObjectsByType,
│   │                                  useLazyObject(id, user)
│   ├── useChat.ts                     chat actions, ingestChatState path
│   ├── useFieldRef.ts                 ref-field hook
│   └── useFieldStore.ts               field-level subscription
│
├── lib/                               (utilities — api client, helpers)
│
├── types/                             (domain types: Message, Channel, etc.)
│
└── components/
    ├── App.tsx primary layout
    ├── MessageList.tsx                chat messages (uses useChat)
    ├── MessageInput.tsx               input with commands
    ├── ChannelSidebar.tsx             channel nav
    ├── CommandPalette.tsx             cmdk integration
    ├── BashTerminal.tsx               xterm + just-bash shell, middlelayer audit
    ├── TypeHierarchy.tsx              live debug tree grouped by virtualType /
    │                                  runtimeType / path
    ├── DebugConsole.tsx               floating debug panel, tabs: L0 Log /
    │                                  Type Hierarchy / Bash
    └── RuntimeAtomicDemo.tsx          ← PR #30. Dual Lexical (editor + viewer)
                                        over one Store object, local-first vs
                                        server-gated mode toggle. Reach via
                                        #runtime-demo URL hash.
```

### Primitive summary

#### `data/types.ts` — **FieldOp as the one primitive**

```ts
interface FieldOp {
  seq: number               // monotonic per writer
  writer: string
  ts: string                // ISO
  objectId: string
  fieldName: string
  op: 'set' | 'unset' | 'retype'
  type?: FieldType           // 'value' | 'ref' | 'path_rel' | 'path_abs' | 'placeholder' | string
  content?: unknown
  cause?: { writer; seq }   // causality link
}

interface Field { name; type; content }

interface VirtualObject {
  id: string
  virtualType: string        // inline string, NO catalog
  fields: Map<string, Field>
  version: number            // bumps on any op, drives React subscriptions
}

interface ProjectionSpec {
  name: string
  resolve(obj, store) → Field[]
}

interface VirtualList {      // "Not its own primitive — modeled as a VirtualObject
  id; items: [{id, projection?}]   // with field type='ref' list content"
}

type Cookie = string | number | { order: string | number }
```

Role: one truth layer — append-only log of FieldOps. All objects are derived views rebuilt per version bump. Designed Replicache/CRDT-compatible out of the box.

#### `data/signal.ts` — **inline ~100 LOC micro-lib**

```ts
state(initial)  → { get, set, subscribe }
computed(fn)    → lazy memoized
effect(fn)      → re-runs on tracked dep change
event()         → { emit, on, off }
// auto-tracked deps via a global "current effect" stack
```

Role: primary reactivity engine. Store uses per-object version signals; hooks hook into them via `useSyncExternalStore`.

#### `data/store.ts` — **Store class**

```ts
class Store {
  applyBatch(ops: FieldOp[]) → void      // canonical mutation
  snapshot(id) → VirtualObject | undefined
  get(id)                                 // synonym for snapshot
  subscribe(id, cb) → unsub               // per-object subscription
  version(id)                             // current version signal value
  makeOp(writer, partial: Omit<FieldOp, 'seq'|'ts'>) → FieldOp   // auto-seq, ts
  toJSONL() / fromJSONL(jsonl)            // Langextract-compatible serialize
  registerProjection(spec)
  resolve(id, projectionName) → Field[]   // pure projection resolve
  // RAW_PROJECTION / SERIALIZE_PROJECTION built-in
}
```

Role: **single truth layer for the client**. All mutations flow through `applyBatch`. All reads flow through `snapshot`/`resolve`. Subscriptions per object (not global) for scoped reactivity.

#### `data/lazy.ts` — **virtual object as self-describing query**

```ts
collectMissingRefs(obj, store) → refIds[]
resolveMissing(refIds, fetch) → Promise<void>
ingestQueryNode(node, writer)          // fold query response back as FieldOps
resolveForObject(id, user)             // wire-in for useLazyObject
```

Role: when a VirtualObject has `ref` or `path_abs` fields pointing at unknown ids, walker collects them, triggers batch fetch, ingests response at the same atomic paths where nulls were. Object structure *is* the query.

#### `runtime/types.ts` — **RuntimeAdapter interface**

```ts
type RuntimeType = 'virtual' | 'signal' | 'vfs' | 'replicache' | 'lexical' | 'crdt' | 'quickjs'

interface RuntimeObject {
  id; runtimeType; branchMeta; schema
  getField(name); setField(name, v); applyOp(op); subscribe(cb); serialize()
}

interface RuntimeAdapter<B> {
  type: RuntimeType
  create(id, schema, branchMeta): RuntimeObject
  read(id): RuntimeObject | undefined
  apply(id, op): void
  subscribe(id, cb): Unsub
  serialize(id): string
  hydrate(id, serialized): void
}
```

Role: pluggable backend per runtime type. Same interface, different storage/reactivity mechanism.

#### `runtime/layer.ts` — **RuntimeLayer**

```ts
class RuntimeLayer {
  registerAdapter(adapter)
  instantiate(id, schemaRef)
  applyOp(id, op)
  readObject(id)
  subscribeObject(id, cb)
  serializeObject(id)
  resolveRuntimeType(schemaRef)       // inherits through schema chain, deep-merges config
}
```

Role: router between schema-declared `runtimeType` and actual adapter. Inheritance walker = `extends`-chain resolution with config merge.

#### `runtime/middlelayer.ts` — **exec interceptor**

```ts
class Middlelayer {
  exec(ctx: {cmd, requester}, callFn)     // wraps any exec call
  onBeforeExec(hook); onAfterExec(hook)
  getCallLog() → Array<{ctx, result}>
}
```

Role: captures prev state + new state + call metadata on every exec. Writes `<field>._exec.<callId>.{cmd, requester, prev, ts}` as shadow metadata alongside mutated paths. Enables provenance-aware UI (`current_value` projection vs `exec_history` projection).

#### Adapters

- `virtual.ts` — delegates to `Store` (baseline, idempotent on existing ops)
- `signal.ts` — in-memory reactive via signal micro-lib (opHistory + Signal<Map>)
- `vfs.ts` — file-backed via just-bash `InMemoryFs` — per-object `{basePath}/meta.json + fields.json + ops.jsonl`, WeakMap sync cache bridges async VFS with sync API

Pending (not yet built):
- `replicache.ts` — protocol-only via `/pchat/exec` cmds
- `lexical.ts` — @lexical/* editor backing (partially prototyped in `RuntimeAtomicDemo.tsx` but not extracted)
- `quickjs.ts` — untrusted code isolation
- `crdt.ts` — SyncKit Fugue/Peritext

#### Hooks

```ts
useStore()                       → store instance + version
useVirtualObject(id)             → VirtualObject reactive
useProjection(id, projectionName) → Field[] reactive
useObjectsByType(virtualType)    → VirtualObject[] filtered
useLazyObject(id, user)          → object + auto-fetch missing refs on render
useChat()                         → chat actions, calls ingestChatState on refresh
useFieldRef(id, field)            → ref-field value
useFieldStore()                   → field-level primitives
```

Role: React-side reactivity bridge. Each uses `useSyncExternalStore` against per-object version signal.

### Dependency graph

```
                      types.ts (FieldOp, Field, VirtualObject, ProjectionSpec)
                           ▲
                           │
          ┌────────────────┼────────────────┐
          │                │                │
      signal.ts         store.ts          lazy.ts
                           ▲                ▲
                           │                │
                     ┌─────┴───────────┐    │
                     │                 │    │
                  hooks/*       runtime/layer.ts ──── uses Store via VirtualAdapter
                     ▲                 ▲                │
                     │                 │                ▼
              components/*      runtime/adapters/*    middlelayer.ts ── wraps exec
                     ▲                 ▲                              (any adapter)
                     │                 │
                  App.tsx      RuntimeAtomicDemo.tsx
                                  (#runtime-demo)
                                      │
                                      ▼
                                Lexical core + BashTerminal
                                + direct store.applyBatch calls
```

**What RuntimeAtomicDemo actually uses**:
- `getStore()` — directly
- `getMiddlelayer()` — read call log for audit display
- `BashTerminal` — as one of three panels
- Two `LexicalContainer` components — editor + viewer over same Store object

Does NOT use `getRuntime()` / adapters — writes FieldOps directly via `store.applyBatch([store.makeOp(...)])`. The "runtime" in the name refers to the invariant (immediate projection = atomic in the database-transaction sense), not to `RuntimeLayer`.

---

## Part III — Shared Invariants

Both lines independently arrived at these. They're **language-agnostic** and survive regardless of which line becomes canon.

1. **One primitive + derived views** — atom_prototype: `VirtualTypeEntry`; sandbox: `FieldOp`. Different shape, same discipline: all higher structures are projections.

2. **Identity is addressable, names are overlays** — atom_prototype: hash + Namescope aliases; sandbox: opaque id + (no catalog yet). Both reject "name = identity".

3. **Projections are pure functions** — atom_prototype: `Extractor.run(rows) → string` / `spanProjections.*`; sandbox: `ProjectionSpec.resolve(obj, store) → Field[]`. Cacheable, sandbox-executable.

4. **Immediate projection invariant** — atom_prototype: pure fns + reactive refs; sandbox: local-first mode + `store.applyBatch` + subscribe bump. User-facing view never waits for ack.

5. **Append / rebuild, not mutate** — atom_prototype: `NestedAtomicList.add` appends to ordered Map; sandbox: FieldOp log strictly append. Modification = new entry in log, old entries untouched.

6. **Shadow metadata alongside values** — atom_prototype: `cell.metadata.atom.*`, Namescope aliases; sandbox: `<field>._exec.<callId>.*`. Provenance / extensions live next to data without polluting it.

7. **Per-object subscription, not global reactive graph** — atom_prototype: Vue reactivity per-instance; sandbox: signal per-objectId. Scoped = scalable.

8. **Polymorphism by naming** — atom_prototype: `type: string` on VirtualTypeEntry + per-category extractors; sandbox: `runtimeType: string` on RuntimeObject + adapter registry. Same pattern.

9. **Hierarchical scopes** — atom_prototype: `LangScope.parent` chain; sandbox: `branchMeta` + schema inheritance chain. Same idea via different plumbing.

---

## Part IV — Term Collisions

Same word, different meaning. This is the biggest pitfall for a new project.

| Term | atom_prototype | sandbox |
|------|----------------|---------|
| **`Atom`** | compute unit `{id, kind, inScope, op, outScope}` — an OPERATION | not used (word appears only in `RuntimeAtomicDemo`, meaning "atomic projection") |
| **"virtual object"** | `VirtualTypeEntry` — type catalog entry, hash-addressed wrapper | `VirtualObject` — derived view over FieldOp log, id-addressed, rebuilt per version |
| **"virtual list"** | `NestedAtomicList` / `ArrayAtomicList` — first-class collection with hashing | `VirtualList` — helper type; *not a primitive*, modeled as VirtualObject with ref-typed fields |
| **"projection"** | `Extractor.run(rows) → string` (mostly output formatting) | `ProjectionSpec.resolve(obj, store) → Field[]` (field transformation) |
| **"namescope"** | Explicit class with personal/shared/parent alias layers | No direct equivalent; `virtualType: string` inline tag |
| **"wrapper"** | Express-middleware style decoration of compute-atom execution | Middlelayer = exec interceptor; or adapter = backend implementation |
| **"mount"** | `mountManager` for Vue components in floating cells | — (doesn't exist in this form) |
| **"runtime"** | Module is atom/mount/container plumbing | `runtime/` = adapter-polymorphic layer with Middlelayer + RuntimeLayer |
| **"signal"** | — (Vue's reactivity implicit) | First-class micro-lib: `state/computed/effect/event` |
| **"scope"** | `LangScope` (hierarchical doc + lists + namescope) | branchMeta + schema inheritance |
| **"content"** | — | `FieldOp.content` = the payload value |

Rule of thumb for new project: **never reuse a word without glossary entry**. Pick terms fresh or explicitly alias.

---

## Part V — Divergences (architectural)

Beyond terminology — the two lines differ on real structural choices.

### 1. Identity model

- **atom_prototype**: content-hash via `computeAtomicHash(value)`, two identical payloads share id
- **sandbox**: opaque `id: string`, identical content produces distinct FieldOps (by `seq`, `writer`), dedup non-automatic

**Consequence**: atom_prototype natively dedups messages, reactions, spans; sandbox natively preserves history / edit provenance. Different defaults, different trade-offs.

### 2. Mutation model

- **atom_prototype**: imperative on class instances (`list.add(x)`, `cell.pos.x = 100`) — Vue reactivity propagates
- **sandbox**: append FieldOp to log via `applyBatch`, Store rebuilds objects, subscribers fire

**Consequence**: atom_prototype has no mergeable history; sandbox is CRDT/Replicache-ready out of the box.

### 3. Type system

- **atom_prototype**: `Namescope` catalog of types, aliases resolve through cells + parent chain
- **sandbox**: `virtualType: string` inline per object, no catalog, schema inheritance via `RuntimeLayer.resolveRuntimeType`

**Consequence**: atom_prototype supports named virtual types first-class; sandbox supports schema inheritance + polymorphic adapters first-class. Two complementary type-oriented features, each missing the other.

### 4. Collection primitives

- **atom_prototype**: `AtomicListBase<T>` — two variants (array / nested), hashing built in
- **sandbox**: no dedicated primitive — lists are VirtualObjects whose ref-typed fields carry item ids

**Consequence**: atom_prototype has ergonomic collections; sandbox has uniform "everything is a FieldOp" discipline.

### 5. Compute model

- **atom_prototype**: `Atom` (op unit) + `AtomRegistry.run()` + wrapper chain — explicit dataflow graph
- **sandbox**: no compute primitive at this layer — logic is React components + direct `applyBatch` + async effects

**Consequence**: atom_prototype can declare "X happens when Y" via atom graph; sandbox leaves that to React + effects.

### 6. Reactivity engine

- **atom_prototype**: Vue 3 ref/shallowRef/computed/watch — implicit tracking
- **sandbox**: hand-rolled signal micro-lib + useSyncExternalStore — explicit

**Consequence**: Vue side has more ergonomic reactivity out of the box; sandbox side has finer control + smaller runtime.

### 7. Sync / storage

- **atom_prototype**: local only, synckit stubbed — no server story
- **sandbox**: Replicache-compatible FieldOp format (per-writer seq, cookie-based delta), `/pchat/exec` + `/pchat/batch` + JSONL hydrate, VfsAdapter for persistence

**Consequence**: sandbox is the "real" runtime; atom_prototype is a lab.

### 8. Relation to Lexical

- **atom_prototype**: Lexical mounted as container type via `mount.ts` → Vue component wrapping core editor
- **sandbox**: Lexical mounted as dual instance (editor + viewer) over one Store object, PR #30 live; architecture treats Lexical state as just-another-projection

**Consequence**: sandbox has the more interesting Lexical integration (runtime-backed projection) — a blueprint for LexicalAdapter.

### 9. Projections scope

- **atom_prototype**: output-format oriented (csv/json/md/…) + identity projections (mime-bundle, row-index)
- **sandbox**: field-transformation oriented (resolve refs, filter fields, overlay fields)

**Consequence**: they cover different axes. Both needed for a full system.

### 10. Persistence

- **atom_prototype**: Jupyter `.ipynb` round-trip (canvas-notebook), ad-hoc JSON per view
- **sandbox**: JSONL (Langextract-compatible), per-object VFS dirs, `runtime/containers/*` FS layout

**Consequence**: atom_prototype has richer interchange format story (.ipynb, canvas metadata); sandbox has richer native storage.

---

## Part VI — Starter Blueprint for a Parallel Project

Proposed target: **one line, unified, fresh code, cherry-picked ideas from both references.**

### Stack choice

React-based (aligns with sandbox; broader ecosystem for shadcn/Radix/ahooks) **OR** Vue-based (aligns with atom_prototype; lighter runtime). Recommend React + signal micro-lib + Tailwind 4 — inherits sandbox's maturity, keeps room for Lexical interop already proven there.

### Layer order (bottom to top)

```
L0  Log                 — append-only FieldOp (from sandbox) — sync-ready, history-preserving
L1  Wrapper             — VirtualTypeEntry (from atom_prototype) — type catalog, aliases
L2  Collections         — AtomicListBase<T> (from atom_prototype) — ergonomic, hash-aware
L3  Registry            — Namescope + cells (from atom_prototype) — relative names, scope
L4  Reactivity          — signal micro-lib (from sandbox) — scoped per-id
L5  Compute             — Atom + Registry + wrappers (from atom_prototype, rename to AtomOp)
L6  Projection          — ProjectionSpec + Extractor (merge both conventions)
L7  Adapters            — RuntimeAdapter<B> (from sandbox) — virtual / signal / vfs / lexical / ...
L8  Middlelayer         — exec interceptor (from sandbox) — shadow metadata
L9  UI                  — hooks, components, views
```

Each layer **must** be independently testable (≥10 unit tests per layer). Each layer **must** have zero knowledge of layers above it.

### First worked example (the unification): `Atom`

The best example precisely because "atom" means different things today. Unify by splitting:

```ts
// L1/L2 — data atom (wrapper)
interface Atom<P = unknown> extends VirtualTypeEntry {
  hash; type; payload: P; tags?
}

// L5 — compute atom (renamed)
interface AtomOp {
  id; kind: 'op'|'projection'|...; inScope: AtomHash[]; op: OpSpec
  outScope: AtomHash[]; wrappers: string[]; tags: string[]
}
```

**Contract**:
- `AtomOp.inScope` / `.outScope` hold `AtomHash` (not `ref` strings) pointing to `Atom<P>` entries in the Namescope.
- Running an AtomOp = `registry.run(id)`:
  1. For each inScope hash: `entry = namescope.get(hash)` → `payload`
  2. Apply op + wrapper chain
  3. Write output as FieldOp: `{op:'set', objectId: outScope hash, fieldName:'value', content: output}`
  4. Store emits version bump on affected objects
  5. Subscribed views re-render
- Projection atoms write to ephemeral out-scope (not logged) — read-only.
- Mutation atoms write to logged out-scope — contributes to truth.

**Why this is a good first example**:
- Exercises every layer L0-L8
- Forces terminology split: Atom (data) ≠ AtomOp (compute)
- Natural test cases: register 3 atoms (spawn, transform, project) → run them → assert log shape + projection output
- Scales to the messy scenarios (bridgeWrapper cross-type, langextract span atomics, extractor catalog) as follow-ups

### Starter skeleton

```
src/
├── l0-log/
│   ├── fieldop.ts               // FieldOp, Field, FieldType
│   ├── log.ts                   // append, readSince(cookie), toJSONL, fromJSONL
│   └── log.test.ts
├── l1-atom/
│   ├── atom.ts                  // Atom<P>, hash(), canonical()
│   ├── atom.test.ts
├── l2-collection/
│   ├── list.ts                  // ArrayAtomicList, NestedAtomicList, computeAtomicHash
│   └── list.test.ts
├── l3-namescope/
│   ├── namescope.ts             // Namescope, NamescopeCell, aliases, parent chain
│   └── namescope.test.ts
├── l4-signal/
│   ├── signal.ts                // state/computed/effect/event — copy-adapt from sandbox
│   └── signal.test.ts
├── l5-atomop/
│   ├── atomop.ts                // AtomOp, AtomOpRegistry, wrappers
│   └── atomop.test.ts
├── l6-projection/
│   ├── projection.ts            // ProjectionSpec + Extractor catalog (unified)
│   └── projection.test.ts
├── l7-adapters/
│   ├── types.ts
│   ├── virtual.ts
│   ├── signal.ts
│   ├── vfs.ts                   // just-bash or BrowserFS or OPFS
│   ├── lexical.ts               // ← first big integration test
│   └── adapters.test.ts
├── l8-middlelayer/
│   ├── middlelayer.ts
│   └── middlelayer.test.ts
└── l9-ui/
    ├── hooks/
    │   ├── useAtom.ts
    │   ├── useProjection.ts
    │   └── useLazyAtom.ts
    ├── components/
    │   ├── BashTerminal.tsx     // port from sandbox
    │   ├── TypeHierarchy.tsx    // port + generalize
    │   └── AtomDemo.tsx         // first worked example
    └── App.tsx
```

Each layer's tests pass **before** building the next layer.

### Build / tooling

```
React 19 + @vitejs/plugin-react-swc
Vite 6
Tailwind 4 + @tailwindcss/vite
Vitest + happy-dom
typescript 5 strict
eslint 9 + react-hooks + react-refresh
```

Optional later:
- Radix UI (once UI needs real components)
- @tanstack/react-query (when server sync comes)
- just-bash + @xterm (for BashTerminal port)
- Lexical 0.43 + @lexical/{rich-text, history, utils, selection}
- synckit (when workers are needed)

### What NOT to port

- Canvas Notebook (`canvas-notebook.ts` / `CanvasNotebookView.vue`) — standalone feature, port later if needed for ipynb interop
- Mount manager (`mount.ts`) — Vue-specific, rewrite React-native if/when needed
- React-query integration from sandbox — bring in when server routes land, not before
- All chat-specific components from sandbox (MessageList, ChannelSidebar, CommandPalette) — feature, not foundation
- `RuntimeAtomicDemo.tsx` in its current form — good reference for immediate-projection invariant test, but re-derive cleanly

### What to port almost verbatim

- `data/signal.ts` from sandbox — ~100 LOC, proven
- `atomic-list.ts` from atom_prototype — 20 tests, generic, portable to TS
- `namescope.ts` from atom_prototype — 16 tests, straightforward
- `FieldOp` shape from sandbox types.ts
- `Middlelayer` pattern from sandbox runtime/middlelayer.ts (not code — pattern)

---

## Part VII — Integration Trajectory (how the two lines meet)

Given the parallel project exists, the two existing lines can eventually merge via:

### Stage 1 — terminology alignment
- Rename sandbox `VirtualObject` → `Atom` (or keep both as aliases during transition)
- Rename atom_prototype `Atom` → `AtomOp`
- Document in project CLAUDE.md

### Stage 2 — Atom layer extraction
- Build the unified Atom layer in the parallel project
- Export it as standalone package (`@project/atomic-core` or similar)
- Let both original lines depend on it without other changes

### Stage 3 — FieldOp log under Atom
- Wire the FieldOp log as the truth layer beneath Atom in the parallel project
- Port to sandbox side as the primary truth path (already is)
- Port to atom_prototype side as optional undo/history feature

### Stage 4 — Adapter polymorphism
- Port `RuntimeAdapter<B>` pattern to parallel project
- Implement `LexicalAdapter` — this is where sandbox's PR #30 becomes a proper extracted adapter (not inline demo code)
- Other adapters (replicache, crdt, quickjs, jupyter) slot in later

### Stage 5 — UI convergence
- Pick React (sandbox side) as UI platform for parallel
- Port BashTerminal, TypeHierarchy, DebugConsole
- Build `AtomDemo` + `WrappersDemo` equivalents natively in React

### Stage 6 — Server integration
- Parallel project gets `/exec` + `/batch` endpoints from sandbox side
- VfsAdapter becomes one backend among many
- jupyter_layer Python twin (already on `demo/jupyter-on-master`) attaches as `JupyterAdapter`

Each stage is independent. Each can land without the next. None requires killing either existing line.

---

## Part VIII — Reference Paths

### atom_prototype (`wip/atom_prototype/`)
- `src/atom.ts` — compute atom + registry + wrappers
- `src/atomic-list.ts` — AtomicListBase, computeAtomicHash
- `src/namescope.ts` — VirtualTypeEntry, Namescope, NamescopeCell
- `src/mount.ts` — ContainerSpec, mountManager
- `src/extractors.ts` — named projections catalog
- `src/canvas-notebook.ts` — .ipynb + 2D positions
- `src/langextract.ts` — atomic/list/LangScope
- `src/views/*View.vue` — one per module
- `src/*.test.ts` — 109 tests

### koboldcpp-sandbox (`koboldcpp-sandbox/`)
- `src/data/types.ts` — FieldOp, Field, VirtualObject, ProjectionSpec
- `src/data/signal.ts` — signal micro-lib
- `src/data/store.ts` — Store class
- `src/data/lazy.ts` — missing-ref resolver
- `src/runtime/types.ts` — RuntimeAdapter<B>, RuntimeObject
- `src/runtime/layer.ts` — RuntimeLayer
- `src/runtime/middlelayer.ts` — Middlelayer
- `src/runtime/adapters/{virtual,signal,vfs}.ts` — three adapters
- `src/hooks/{useStore,useChat,useFieldRef,useFieldStore}.ts` — React reactivity
- `src/components/RuntimeAtomicDemo.tsx` — PR #30 dual-Lexical projection
- `src/components/BashTerminal.tsx` — xterm + just-bash

### Design docs already in repo
- `docs/ATOMIC_OBJECT_UNIVERSAL_V0_1.md` — this file's companion: universal wrapper concept (prototype-side)
- `docs/ATOMIC_VIRTUAL_CONTAINER_ARCHITECTURE_DRAFT_V0_1.md` — virtual container architecture (over either line)
- `root/SESSION_T_SNAPSHOT.md` — sandbox-side Phase 1 work snapshot
- `wip/pchat_exec_scope/01-foundation/ARCHITECTURE.md` — L0-L4 layer model (sandbox-side)
- `wip/pchat_exec_scope/02-model/DATA_MODEL.md` — FieldOp-layer primitives (sandbox-side)
- `wip/pchat_exec_scope/03-runtime/COMMAND_MODEL.md` — exec/batch
- `wip/HANDOFF_2026_04_18.md` — atomic-as-RAM-primitive principles
- `wip/SESSION_SUMMARY_2026-04-18.md` — atom_prototype build summary + principles
- `C:\llm\atom-prototype-backup-2026-04-18\` — safety-duplicated tar-backup of atom_prototype (no git)

### External references
- IntelliJ Database plugin — `data/extractors/*.groovy` pattern (source of Extractor design)
- IPython `_repr_mimebundle_` — identity projections pattern
- LangChain — scope/RunnableConfig nesting pattern (LangScope)
- Google langextract — AnnotatedDocument format (langextract.ts wraps this)
- Replicache — push/pull rebase + cookie pattern (FieldOp.seq design)
- Jupyter nbformat 4.5 — .ipynb round-trip (canvas-notebook)
- Lexical 0.43 — editor framework used in both lines

---

## Part IX — First Week Plan (for a starting developer)

Assume solo dev, fresh repo, no inherited code. Start-to-working-AtomDemo path:

**Day 1** — scaffolding
- Initialize React + Vite 6 + TS strict + Vitest
- Tailwind 4
- Skeleton folders L0 through L9

**Day 2** — L0 + L1 + L4 (core)
- Port signal micro-lib from sandbox
- Implement FieldOp append log (std tests: seq monotonic, JSONL roundtrip, cookie delta)
- Implement Atom<P> wrapper (hash, canonical, equality)
- First tests green

**Day 3** — L2 + L3
- Port AtomicListBase from atom_prototype (straight TS translation)
- Port Namescope from atom_prototype (straight TS translation)
- Both test suites green

**Day 4** — L5 (compute)
- Implement AtomOp + registry + wrapper chain (renamed from atom_prototype's Atom)
- First mini-demo: double atom + caching wrapper, all via atomopRegistry

**Day 5** — L6 (projection)
- Unified ProjectionSpec + Extractor catalog
- Register CSV/JSON/raw projections as examples
- Tests: projection purity, catalog registration, cache invalidation

**Day 6** — L7/L8 (adapters + middlelayer)
- VirtualAdapter (delegates to FieldOp log)
- SignalAdapter (in-memory reactive)
- Middlelayer exec interceptor
- Tests: adapter swap, middlelayer shadow metadata

**Day 7** — L9 (first UI)
- AtomDemo component: 2 panels, one writes AtomOp output to store, other reads via useProjection
- Verify immediate-projection invariant by hand
- Screenshot / record the working demo

End of week 1: one full vertical slice, all layers tested, foundation for bigger integrations (Lexical, BashTerminal, chat UI) next.

---

**End of document. This is intentionally exhaustive — for fresh-context resumption and parallel-project bootstrap, explicitness beats brevity.**
