# Session Summary — 2026-04-17/18

This backup contains the full output of one architectural design + prototype
implementation session. Written for fresh-context resumption.

## Where things live

```
C:\llm\atom-prototype-backup-2026-04-18\
├── SESSION_SUMMARY.md          ← you are here
├── HANDOFF_2026_04_18.md       ← original handoff doc
├── RUNTIME_REFS_MAP.md         ← runtime references taxonomy
├── CLAUDE.local.md             ← local CLAUDE.md preserved (moved aside before pull)
├── atom_prototype/             ← Vue 3 + Vite prototype, 9 modules, 109 tests
└── pchat_exec_scope/           ← architecture docs (canonical)
```

The same files also live under
`C:\llm\KoboldCPP agentic sandbox\wip\` in the main repo (untracked at the
time of writing; commit when ready). Backup is the safety duplicate.

Git state at end of session:
- Main repo branch: `codex/virtual-container-arch-dump` (commit `b57e6420`)
- Just-merged: `origin/master` (commit `2438c775`) into current branch
- Untracked-but-real session work: `wip/atom_prototype/`, `wip/pchat_exec_scope/`,
  `wip/HANDOFF_2026_04_18.md` — preserved through pull, ready to commit

---

## What was built

### Atom Prototype (`wip/atom_prototype/`)

Vue 3 + Vite 5 + Lexical core single-page app, multi-module hub on one port
(5177). 9 internal routes plus iframe workbench plus reverse proxy
(`server.proxy`) for external modules. Build-time virtual modules via unplugin
plus path aliases via `@rollup/plugin-alias`. Vitest suite, 109 passing.

**Core primitives** (`src/`):
- `atom.ts` — Universal Atom + AtomRegistry + wrapper middleware (logging,
  timing, caching). Atom shape: `{id, kind, inScope, op, outScope, payload,
  tags, wrappers}`. Wrapper chain runs as Express-style middleware
  (around-style with `next()`).
- `atomic-list.ts` — two list variants over the same base interface:
  `ArrayAtomicList` (positional) and `NestedAtomicList` (hash-keyed with
  structural dedup). Hash composed as `<localType>(<fields>)|<type>:<value>`,
  human-readable. Round-trip helpers.
- `namescope.ts` — two-detached-list aliasing pattern. Right-side `Namescope`
  (virtual type catalog + shared aliases + per-cell personal aliases).
  Left-side `NamescopeCell` (cellId + ref to one Namescope, personal-first
  resolution). One-way: cells → scope, scope does not track cells.
- `mount.ts` — ContainerSpec auto-mount wrapper + bridge wrappers for
  cross-type composition (atom outputs become live Vue component instances
  in floating cells).
- `extractors.ts` — IntelliJ-Database-style named projections catalog. Two
  catalogs: collection-level extractors (CSV/JSON/MD/SQL-Insert/Python-DF/
  Pretty/ipynb) + aggregators (COUNT/SUM/AVG); single-item identity
  projections (JSON/CSV-line/Key-Value/SQL-single/Primary-key/Atom-URI/
  Row-index/MIME-bundle a la Jupyter `_repr_mimebundle_`).
- `canvas-notebook.ts` — Jupyter `.ipynb` round-trip for 2D-positioned cells.
  `cell.metadata.atom.{pos,size,z,faces,activeFace,widget}` carries our
  extensions; standard Jupyter ignores them, our viewer renders canvas with
  multi-face cards + interactive widgets.
- `canvas-widgets.ts` — widget registry for canvas notebook (table /
  filter / aggregator components).
- `langextract.ts` — wraps Google's langextract `AnnotatedDocument` format
  (no LLM). `atomic(span)` makes one Atom per extraction; `groupByClass(doc)`
  builds detached per-class NestedAtomicLists; `LangScope` is a hierarchical
  scope (parent chain) holding doc + lists + namescope + metadata.
- `plugins/atom-snapshot.ts` — unplugin factory exposing atom state as a
  Vite virtual module (`virtual:atom-snapshot`).

**Views** (`src/views/`):
- `HomeView.vue` — module hub landing
- `AtomDemoView.vue` — Atom + Lexical + wrappers (insert / clear /
  projection / cacheable-double atoms)
- `WorkbenchView.vue` — all modules as floating iframes on one canvas
- `WrappersDemoView.vue` — cross-type bridges with mounted Vue containers
- `AtomicListView.vue` — array vs nested side-by-side with live hash preview
- `NamescopeView.vue` — cells / catalog / shared aliases / personal aliases
  / live resolver
- `ExtractorsView.vue` — table with right-click context menu (Copy as... +
  Extract... + Aggregators)
- `CanvasNotebookView.vue` — drag-and-drop 2D notebook + multi-face cell
  tabs + .ipynb import/export + interactive widgets
- `LangExtractView.vue` — annotated text + per-class lists + namescope +
  alias chain lookup

**Container components** (`src/components/containers/`): LexicalContainer,
LangExtractStub, WebContainerStub.

**Widget components** (`src/components/widgets/`): TableWidget, FilterWidget,
AggregatorWidget.

**Tests** (`src/*.test.ts`): 109 tests across 6 files (atom, atomic-list,
namescope, extractors, canvas-notebook, langextract). All passing.

**Build / scripts**:
- `npm run dev` — http://localhost:5177
- `npm run build` — vue-tsc + vite build
- `npm test` / `npm run test:watch` / `npm run test:ui`
- `npm run typecheck`

### Architecture docs (`wip/pchat_exec_scope/`)

Pre-existing canonical architecture from the broader project; updated this
session:
- `README.md` — read order
- `01-foundation/ARCHITECTURE.md` — invariants and layer model (L0–L4)
- `01-foundation/RUNTIME_STACK.md` — 5-component stack (extended this session
  with Wasp deferred, Jupyter adoption strategy, References & inspirations,
  Deferred / future work, plus FS-first invariant softening)
- `01-foundation/LEXICAL_ADOPT_PLAN.md` — narrow Lexical-specific mapping
- `02-model/DATA_MODEL.md` — primitives shapes
- `03-runtime/COMMAND_MODEL.md` — exec / command resolution
- `99-handoff/HANDOFF.md` + `IMPLEMENTATION_PLAN.md` + `BRANCH_NOTES.md`

---

## Architectural principles distilled

The session walked through architecture iteratively. Key principles ended at:

1. **Atoms are MOV-wrapped references.** Same operational structure across
   sizes; only payload differs. Identity by content hash.

2. **Virtual = projection-claim that resolves to a named atom in a local
   scope.** Transient lifecycle stage; projections hold structural shape,
   resolution attaches concrete refs.

3. **Two-direction symmetry**: path side ↔ value side. Both are projections
   of the same lens (Field). Same wrapping rule, mirror-applied.

4. **Storage is a projection, not a model.** FS-first, OPFS, SQLite, IPYNB
   — all are persistence projections. No hard FS-first invariant; per-scope
   storage choice.

5. **Names are opt-in overlay over hash UIDs.** Two-detached-list namescope
   pattern: right side holds catalog + aliases, left side cells query.
   Personal-first then shared. One-way arrow.

6. **Wrappers decorate without changing identity.** Express-middleware-style
   chain. Composable, runtime-toggleable, identity-preserving.

7. **Same atom, N representations.** Identity projections catalog: one row
   ↦ JSON / CSV-line / SQL / URI / MIME-bundle / etc. Pattern shared with
   IntelliJ Copy submenu and IPython display protocol.

8. **Jupyter format adoption + own UI.** Tie to `.ipynb` for durable
   interchange, render + wrap + extend in our own code. Don't adopt
   JupyterLab as substrate.

9. **Cross-type bridges via wrappers.** `bridgeWrapper(targetAtom, transform)`
   intercepts atom output, transforms shape, downstream auto-mount sees
   transformed payload. Pure composition.

10. **Hierarchical scopes (LangScope).** Parent chain, lookup walks up.
    Parallels LangChain's nested-run pattern.

11. **Resolve = write-path, projection = read-path.** Not bifurcated by
    user — both surfaced through one accessor overload, internal mechanics
    hidden.

12. **Bake-time composition, runtime substitution.** Heavy work moves to
    compile/bake step. Runtime applies single-step substitutions over
    pre-assembled environments. MOV-level cost per access.

13. **Universal hash op.** One generic `hash(content)` operation. Different
    "kinds" of hash are different inputs, not different operations. Vite
    virtual modules are projections of atom state into bundler space, not
    substrate.

14. **Tools selection (refs, not deps)**: see References section in
    `RUNTIME_STACK.md` — Calkit, langextract, zx, Scoop, jid, JSONata,
    IntelliJ Database plugin, JupyterLab + browser-storage, IPython display
    protocol, nbformat, Vite + rolldown-vite, unplugin, Lexical, un-ts/
    synckit, web-container, lexical-yjs, mockforge-recorder.

---

## How to resume in a new chat

Suggested opening message for next session:

> Continuing from `C:\llm\atom-prototype-backup-2026-04-18\SESSION_SUMMARY.md`.
> Atom prototype lives in `wip/atom_prototype/` (Vue 3 + Vite, 9 modules, 109
> tests). Architecture docs in `wip/pchat_exec_scope/`. Recently merged master
> into `codex/virtual-container-arch-dump` branch. Backup folder has CLAUDE.local.md
> + full prototype + docs as safety copy.

Then point at whichever direction is relevant — likely one of the
"Next directions" below.

---

## Next directions (pick one when ready)

Captured during the session, deferred or partially built:

**Tighter integrations** (extending what's there):
- Cross-container synckit wiring (worker bridge for projection sync)
- Lexical interactive feedback loop (editor change → atom → editor again)
- Atom composition / chain primitive (atom A output feeds atom B input)
- Browser-side compile atom (esbuild-wasm wrapped in atom op)
- Wired widget cells in canvas notebook (filter actually filters table)
- launch-editor wire (jump-to-source on click)

**New surfaces** (new modules):
- AtomExplorerView (jid-style incremental drill-down over registry)
- JSONata extractor (M:N query DSL in extractor catalog)
- Layout projections (`schema.layouts/*.groovy` analog — file-placement projection)
- Identity projections in NamescopeView (right-click virtual type → copy as...)
- Atom registry → Scoop manifest round-trip (declarative atom store)
- zx atom-op backend (`OpSpec.zx`)

**Architectural**:
- Custom Jupyter resolver (Atomic-typed Raw cells via projection refs) — see
  `wip/pchat_exec_scope/01-foundation/RUNTIME_STACK.md` deferred-work section
- Wasp adoption (deferred until L2 runtime stable per agreement)
- LangChain.js bridge (if multi-agent scope needed)
- Multi-user CRDT via @lexical/yjs (deferred)

**Operational**:
- `git add wip/atom_prototype wip/pchat_exec_scope wip/HANDOFF_2026_04_18.md`
  + commit + push to remote (we have backup, but committing makes it official)
- Fresh dev environment validation: `cd wip/atom_prototype && npm install &&
  npm test && npm run dev`

---

## Test + build commands (for resumption verification)

```bash
cd "C:\llm\KoboldCPP agentic sandbox\wip\atom_prototype"
npm install              # if node_modules missing (it is in backup)
npm test                 # 109 tests should pass
npm run typecheck        # vue-tsc clean
npm run build            # vite build clean
npm run dev              # http://localhost:5177
```

If using backup folder directly: `cd C:\llm\atom-prototype-backup-2026-04-18\
atom_prototype` and same commands.

---

## Files inventory (atom_prototype)

```
src/
├── App.vue              top-level shell with router-view + nav
├── main.ts              entry, installs router
├── router.ts            route + moduleEntries registry
├── shims.d.ts           Vue + virtual-module ambient types
├── atom.ts              Atom + Registry + wrappers (3 pre-baked)
├── atom.test.ts         10 tests
├── atomic-list.ts       Array + Nested AtomicList
├── atomic-list.test.ts  20 tests
├── namescope.ts         Namescope + NamescopeCell
├── namescope.test.ts    16 tests
├── extractors.ts        Extractors + IdentityProjections + ipynb + mimebundle
├── extractors.test.ts   24 tests
├── canvas-notebook.ts   .ipynb round-trip + multi-face + widgets
├── canvas-notebook.test.ts 18 tests
├── canvas-widgets.ts    widget registry
├── langextract.ts       atomic + groupByClass + LangScope
├── langextract.test.ts  21 tests
├── mount.ts             ContainerSpec + auto-mount + bridge wrappers
├── plugins/
│   └── atom-snapshot.ts unplugin virtual module
├── workers/
│   └── resolver.worker.ts  synckit stub (deferred)
├── components/
│   ├── EditorHost.vue
│   ├── AtomDemo.vue
│   ├── VirtualObjectDemo.vue
│   ├── containers/
│   │   ├── LexicalContainer.vue
│   │   ├── LangExtractStub.vue
│   │   └── WebContainerStub.vue
│   └── widgets/
│       ├── TableWidget.vue
│       ├── FilterWidget.vue
│       └── AggregatorWidget.vue
└── views/
    ├── HomeView.vue
    ├── AtomDemoView.vue
    ├── WorkbenchView.vue
    ├── WrappersDemoView.vue
    ├── AtomicListView.vue
    ├── NamescopeView.vue
    ├── ExtractorsView.vue
    ├── CanvasNotebookView.vue
    └── LangExtractView.vue

vite.config.ts           plugins + dev server proxy + COOP/COEP headers
tsconfig.json            strict TS
package.json             deps: vue 3, lexical, @lexical/{rich-text,history},
                         synckit, vue-router, @rollup/plugin-alias, unplugin
                         devDeps: vitest, vue-tsc, vitejs/plugin-vue, vite
index.html               dark Rosé-Pine-ish theme
README.md                module hub overview + run instructions
```
