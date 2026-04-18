# Runtime Stack

## Status

Architectural decision: runtime is a 5-component container set, each component
owning a distinct domain. Not a monolithic substrate.

This document supersedes the earlier narrow `LEXICAL_ADOPT_PLAN.md` framing.

## Invariant softening note (2026-04-17)

- **FS-first storage (`_meta.json` + `_data.json` + `root/` tree) is NOT a hard
  architectural invariant** for the new runtime. It was the shape used by the
  legacy pipeline-chat and reflected in CLAUDE.md, but we have agreed on a
  **softer invariant**: no forced binding to concrete file layouts or to the
  local filesystem at all.
- **Wasp + Wasp DSL will be adopted** as the primary authoring / declaration
  layer. For the near-term scope ("пока достаточно") Wasp alone covers the
  authoring surface; concrete storage layer is a downstream decision, not a
  foundational constraint.
- mockforge / OPFS / git-versioned FS are all valid candidates for persistence
  when needed, but none are mandatory. Persistence is a projection target,
  chosen per scope, not a universal requirement.

---

## Components

### 1. Lexical — Text Canvas / Editor

Role: text sandbox with event-sourced content editing.

Provides:
- EditorState as immutable content snapshot
- Command dispatch with priority propagation
- Node transforms (bind cascade in our terminology)
- Double-buffered updates
- Native history / undo-redo / replay (`@lexical/history`)
- DevTools with play slider (`lexical-devtools`)
- Headless mode for server-side operation (`@lexical/headless`)
- Extension API for domain-specific registration (`@lexical/extension`)

Scope:
- Text content, rich text, nodes
- Not shell, not exec, not markup overlays

### 2. web-container — Shell / Exec Runtime

Role: bash-like execution carrier with UI.

Reference: `wip/runtime_refs/web-container` — in-browser TS/JS IDE.

Provides (adapt the pattern, not the codebase literally):
- Monaco editor for authoring
- xterm terminal for output
- Bash command interpreter (our `just-bash` already installed serves this)
- QuickJS-WASM for sandboxed JS execution
- OPFS + IndexedDB for persistent VFS
- 3-worker architecture: container orchestration + esbuild compilation + quickjs execution

Pairs with:
- `cmdk` (already installed) for command palette entry
- `@xterm/xterm` (already installed) for terminal rendering

Scope:
- Shell commands, exec flows, runtime carrier
- Not text editing (that's Lexical)
- Not collaboration (that's synckit)

### 3. mockforge-recorder — Persistence via Mock Layer (optional)

Role: projection checkpoint storage when persistence is needed. Unifies
persistence and test-replay. **Not a foundational layer** — engages only
per-scope when a component needs session persistence.

Rust crate: `mockforge-recorder` (https://lib.rs/crates/mockforge-recorder).
CLI: `mockforge` — run as sidecar service, not embedded.

Usage pattern:
- Runtime projection checkpoints serialize as mock HTTP endpoints
- web-container / Lexical / server all dump state via recorder
- Schema auto-generated from captured request/response pairs
- Restore session: replay from mock → state reconstitutes
- Mock IS the checkpoint store — no separate persistence layer

Integration: mockforge runs as local service (`cargo install mockforge-cli`);
Node / Python processes talk to it over HTTP. No Node bindings needed.

Scope:
- Session persistence, replay fixtures, schema generation
- Not real-time sync (that's synckit)

### 4. langextract (repurposed) — Agentless Markup / Shadow Layers

Role: text-space markup with range-tied metadata. Stripped of LLM dependency.

Original: Google's `langextract` uses LLMs to extract structured data from text
into source-grounded spans. We repurpose its markup primitives (char ranges, tag
classes, attributes) without the LLM extraction path.

Pattern: shadow layers.
- Text = L1 truth, single-sourced
- Markups = shadow projections binding to char ranges
- Multiple concurrent markups coexist, mutually unaware
- As text mutates, markup ranges auto-adjust via range rebasing
- Accessor-overload applied to ranges: each shadow layer overloads access
  to its tagged range transparently

Example use cases:
- Link resolution in text chars (range → link target)
- Citation / reference metadata (range → source doc)
- Completion / hint anchors (range → hint payload)
- Annotation layers per user / per projection kind

Integration path:
- langextract output format (`AnnotatedDocument` JSON with extractions array)
  is shape-compatible
- We write a pure-JS implementation using that format, no LLM call path
- Shadow layers serialize as extraction arrays alongside text

Scope:
- Markup overlays on text content
- Not general metadata (that lives on runtime objects)
- Not structural editing (that's Lexical nodes)

### 5. un-ts/synckit — Projection Sync + Worker Bridge

Role: (a) sync-looking async across worker boundaries, (b) projection delivery.

Package: `synckit` on npm (https://github.com/un-ts/synckit).
Mechanism: Atomics + SharedArrayBuffer for blocking wait on worker return.

Two capabilities, same primitive:

**Worker bridge**: `createSyncFn(workerPath)` returns a function that looks
synchronous from caller perspective, blocks main thread on `Atomics.wait`
until worker returns. Removes async plumbing from cross-worker calls.

**Projection sync**: our architecture is single-writer (SoT) + many-reader
(projections). Projection updates flow one-way from source to subscribers.
synckit provides the delivery primitive: subscribers pull projections via
blocking sync call, source publishes via worker-to-worker message.

Why not yjs:
- yjs solves CRDT convergence across multiple concurrent writers
- Our architecture has singular truth — no convergence problem
- yjs adds machinery for a problem we don't have
- synckit provides reliable projection delivery without CRDT overhead

Scope:
- Worker boundary coordination
- Projection delivery between runtime components
- Not CRDT, not multi-writer merge

### 6. Wasp + Wasp DSL — Authoring / Declaration Layer (deferred)

Role: declarative app-shape DSL. Entities, actions, queries, routes declared
once; compiler emits matching runtime code. The "templates own the domain"
principle expressed as a real DSL compiler.

**Status: parked. Do not integrate yet.** Agreement: first settle the runtime
and near-runtime layer (L2 and adjacent — synced projections, interactive
runtime, browser-side compile). Wasp is a later-phase addition that plugs
into that finished layer; wiring it early would couple authoring decisions
to an unstable runtime shape.

Scope (when integrated):
- Declarative app shape, domain declarations, routes, actions
- Compile-time code generation for both server and client
- Not runtime operations (those live in our atom layer)
- Not storage policy

---

## Cross-component interaction

```
                ┌─────────────────┐
                │   User / Agent  │
                └────────┬────────┘
                         │
              ┌──────────▼─────────┐
              │ cmdk palette / UI  │
              └──┬──────┬──────┬───┘
                 │      │      │
     ┌───────────▼──┐ ┌─▼────┐ ┌▼──────────────┐
     │   Lexical    │ │ xterm│ │  markup       │
     │  (text)      │ │(exec)│ │ (shadow)      │
     └──────┬───────┘ └──┬───┘ └───────┬───────┘
            │            │             │
            │   synckit  │   synckit   │
            │   bridge   │   bridge    │
            │            │             │
     ┌──────▼────────────▼─────────────▼───────┐
     │       Runtime Object Store (SoT)        │
     │   atomic refs, projections, exec log    │
     └───────────────┬─────────────────────────┘
                     │
           checkpoint│   replay/restore
                     │
              ┌──────▼───────┐
              │  mockforge   │  persistence
              │  recorder    │
              └──────────────┘
```

- User input → cmdk / UI → dispatched to relevant container
- Lexical / web-container / markup each operate in their own worker (isolation)
- synckit bridges main thread calls into workers, and pushes projections between them
- Runtime Object Store is the singular SoT — all projections derive from it
- mockforge records projection checkpoints for persistence + replay

---

## Explicit non-goals

To prevent scope creep and premature complexity:

- **No CRDT / yjs** unless multi-writer convergence becomes a requirement
- **No managed collab service** (Liveblocks, Hocuspocus)
- **No monolithic editor** — each container stays focused on its domain
- **No LLM dependency in markup layer** — langextract repurposed without its original extraction path
- **No pchat-specific endpoints** — `/pchat/exec` + `/pchat/batch` stay generic, domain in templates
- **No hard FS-first invariant** — `_meta.json` / `_data.json` / `root/` layout from legacy is softened; storage is a per-scope projection target, not a universal constraint
- **No premature persistence layer** — persistence engages per-component as needed, not globally

---

## Dependencies (deferred until Phase 1 implementation)

```
# Authoring / declaration layer (DEFERRED — do not install yet)
# wasp               # https://wasp-lang.dev/ — DSL + compiler for app shape
                     # Plugged in AFTER L2 runtime is stable. Current focus is
                     # L2 wrapping: synced / interactive / browser-compile.

# Core text canvas
lexical
@lexical/react       # OR use lexical core directly (atom_prototype does the latter)
@lexical/history
@lexical/headless
@lexical/extension
@lexical/rich-text

# Worker bridge + projection sync
synckit              # un-ts/synckit

# Shell / exec carrier (patterns from wip/runtime_refs/web-container)
# just-bash, @xterm/xterm, cmdk — already in koboldcpp-sandbox/package.json
# Optional if full web-container path:
#   @monaco-editor/react, monaco-editor  (authoring surface)
#   esbuild-wasm                         (browser compile)
#   idb                                  (IndexedDB helper)
#   quickjs-emscripten                   (sandboxed JS exec)

# Build-time projections / plugin pattern
unplugin             # universal plugin factory (Vite/Rollup/Webpack/Rspack/esbuild)
@rollup/plugin-alias # canonical path aliases (demonstrates canonical-name → ref)

# Persistence / replay (optional, engages per-scope)
# mockforge — run as sidecar via `cargo install mockforge-cli`

# Markup shadow layer (we write it, uses langextract's AnnotatedDocument format)
# No dependency; reference shape only.

# DX sugar (optional, dev-time only)
launch-editor        # yyx990803 — click UI element → open source file at line
                     # Useful for DevTools / error links / inline inspection.
                     # Nice-to-have, not architectural.
```

All components MIT-ish licensed, production-grade except where noted.

---

## Phase alignment

### Phase 1 — L2 Runtime Primitives (current focus)
- Universal Atom type + registry
- Atom wrapper layer (decoration without identity change)
- Minimum plumbing for synced / interactive / compile-adjacent experiments
- Prototype lives in `wip/atom_prototype/`
- No Wasp yet, no server endpoints yet, no template scaffolding

### Phase 2 — L2 Wrappers + Adjacent Layers
- Synchronous projection delivery (synckit worker wiring)
- Interactive runtime composition (Lexical + atom registry feedback loop)
- Browser-side compile primitives (esbuild-wasm as atom op, rolldown when Node >= 20.19)
- Still no Wasp — these are runtime-adjacent, not authoring

### Phase 3 — Atomic Runtime Refs
- runtime object store with atomic refs
- value refs, relative path refs, projection names
- no value duplication

### Phase 4 — Virtual Objects
- virtual objects assembled from refs
- message / channel / list virtual objects

### Phase 5 — Client Containers
- **Lexical** integration for text content containers (messages, edit fields)
- **xterm + cmdk + just-bash** wiring for shell containers
- **synckit** bridges between UI thread and container workers
- client containers = projection-only render shapes

### Phase 6 — Shadow Markup + Persistence
- **langextract-repurposed** shadow markup engine for text annotations
- **mockforge** sidecar for projection checkpoint persistence
- schema auto-generation from captured state

### Phase 7 — Git / Sandbox / FS Projections (opt-in)
- Git tree projection, sandbox tree projection — only if/when needed
- Legacy FS-first storage (`_meta.json`, `_data.json`, `root/`) becomes one
  possible persistence projection among others, not a foundational layer
- Lazy sync helpers between components

---

## Jupyter adoption strategy

Explicit position on how deeply we integrate with the Jupyter ecosystem:

**Adopt — file format + selective patterns**:
- **nbformat 4.5** as the file-level storage/interchange format. Our Canvas
  Notebook reads/writes valid `.ipynb` with standard `cells[]` + extended
  `cell.metadata.atom.*` for positioning, faces, widgets. Users can open
  files in standard Jupyter (linear render, extras ignored) or our viewer
  (canvas render, widgets interactive).
- **IPython display protocol** (`_repr_mimebundle_`, `text/html`, `text/json`,
  `text/markdown`, …) — already implemented as `mimebundle` identity
  projection in `extractors.ts`. Wire-format compatible with any tool that
  consumes IPython display data.
- **Pattern harvesting** from JupyterLab extensions — check registry before
  implementing new features; cherry-pick TS/JS code when licensing allows.

**Do not adopt — not as UI / runtime base**:
- **JupyterLab as UI substrate** — too heavy, too opinionated, wrong
  abstractions for free-form canvas + atom registry + shadow layers + our
  runtime semantics. Building our own Vue-based viewer gives freedom and
  half the bundle size.
- **Full Jupyter kernel protocol** — heavy ZMQ-based or websocket-based
  surface, tied to Python-first assumptions. Not required for our atom
  runtime. Consider selectively later (Phase 8+) if we need standard kernel
  interoperability; otherwise skip.
- **JupyterHub / Binder / cloud-run conveniences** — server-side
  orchestration outside scope of our local-first atom runtime.

**Potential future move — rebuild pieces in TS**:
- JupyterLab's frontend is a large Lumino/React codebase. If we ever want
  richer notebook-editor features (cell execution, kernel integration,
  widget panels), we extract only the pieces we need and reimplement in our
  TS stack rather than bolting JupyterLab on top.
- Candidate pieces worth extracting (pattern-wise, not code-wise):
  - Cell execution queue semantics (in-order, cancellable, queued)
  - Comm-channel primitive for bidirectional cell-kernel messaging
    (we'd implement via synckit worker bridge instead)
  - MIME renderer registry (map mime-type → renderer component)
  - Side-panel docking model (extension surface composition)

**TL;DR**: tie to `.ipynb` as the durable artifact; render + wrap + extend
all in our own code. "Jupyter gives a great Layer for data/automation, but
our functional envelope is different — we adapt the file, not the shell."

---

## Deferred / future work

### Custom Jupyter resolver with Atomic-typed Raw cells

Observation: Jupyter's `raw` cell type is a passthrough of uninterpreted text. In
a full-scope integration we'd want **our own resolver** over .ipynb content so
that raw cells can be treated as **Atomic-typed containers** whose content is
assembled on-the-fly from **virtual projections**.

Shape:
- A raw cell's source is treated as a projection reference (e.g., a URI like
  `langext://scope-id/class/start-end`, an atom path, or a `Raw(projection_ref)`
  call marker).
- At render time, our resolver walks the reference, resolves via atom registry
  / namescope / LangScope chain, and emits the **current** projection payload
  as the raw cell content.
- Standard Jupyter sees the reference text verbatim (readable, git-diffable)
  and renders it as-is.
- Our viewer renders the live-resolved content — same source file, richer
  display.

Convenient properties:
- Notebook becomes a **composable view** over atom state rather than a
  snapshot of computed output — edits to atoms propagate to all referencing
  notebooks without re-executing kernel cells.
- Raw cells gain Atomic typing: they carry identity (the reference hash) +
  projection family (how to render) + content (resolved on demand).
- Works for embedded projections across notebooks: a reference in notebook A
  pointing at an atom in scope S resolves identically wherever the notebook
  is opened (as long as S is reachable).
- Git-diffable: the stable reference text is what gets committed, not the
  fluctuating resolved payload.

Scope of the work: substantial — requires:
- A resolver module that understands our projection reference grammar
- Integration with atom registry + namescope + LangScope chain lookup
- Mime-type negotiation for the resolved payload (text/plain vs text/html vs
  text/markdown vs custom)
- Optional cache layer for resolved content, with invalidation on atom changes
- UI decisions for the viewer: inline render vs collapsed ref vs live refresh

Not prioritised for the current iteration — the Canvas Notebook prototype
already demonstrates the simpler "custom metadata, standard Jupyter ignores"
pattern. The resolver idea extends that: instead of only carrying extra
metadata, raw cells *reference* atom state and let the resolver produce
content on the fly. Convenient interface; deferred until post-Phase-5 if
still useful by then.

---

## Risks

- **COOP/COEP headers required** for SharedArrayBuffer (synckit) and OPFS (web-container).
  Dev server and production deployment must set `Cross-Origin-Opener-Policy: same-origin`
  and `Cross-Origin-Embedder-Policy: require-corp`. Same constraint applies to both.

- **mockforge CLI as sidecar** — additional process to manage, not an in-process library.
  Trade-off accepted: unified persistence+replay layer worth the orchestration cost.

- **langextract repurpose** is our custom work, not an adopted library.
  Requires writing shadow-layer runtime. AnnotatedDocument format is stable
  (`extraction_class`, `extraction_text`, `char_interval`, `attributes`),
  but the LLM-free runtime is original code.

- **synckit as projection sync** — its primary documented use is worker-boundary async→sync,
  not projection distribution. Our usage extends this via wrapping. Need to validate
  projection-delivery pattern holds at expected scale.

- **web-container reference is hobby code** — not published to npm.
  We adapt patterns (3-worker split, OPFS+IndexedDB storage, QuickJS exec) rather than
  import the project. Implementation effort is ours.

---

## Open questions (resolve during Phase 1–5)

1. Does mockforge's HTTP API match the shape of our projection checkpoints, or do
   we need an adapter layer?
2. Should langextract-repurposed shadow layer live in Lexical extension, or as a
   standalone markup runtime that both Lexical and web-container consume?
3. synckit projection delivery — pull-based (reader blocks for update) vs
   push-based (writer notifies, reader picks up)? Both possible, different perf trade-offs.
4. Worker count — one worker per container type globally, or per-instance?
   Memory pressure vs isolation trade-off.
5. cmdk as universal entrypoint — does it dispatch to Lexical commands directly,
   or always through `/pchat/exec` for consistency?

---

## Migration note from earlier `LEXICAL_ADOPT_PLAN.md`

That doc framed Lexical as THE substrate with other pieces as bridges. This was
too narrow. Correct framing: Lexical is ONE container type among five components.
Each component owns its domain; runtime stack is the set, not any single piece.

The earlier doc's architecture mapping (Lexical primitives ↔ our invariants) still
holds for the text-canvas portion; it's preserved there as reference. The broader
stack lives in this document.

---

## References & inspirations

Tracked projects whose patterns informed this architecture. Linked for future
re-consultation; not runtime dependencies unless explicitly integrated.

### Pipeline / dependency tracking

- **Calkit for JupyterLab** — https://docs.calkit.org/jupyterlab/
  Automates environment management + pipeline orchestration across multiple
  interdependent notebooks. Intelligently determines execution order based on
  input/output dependency tracking; re-runs only stale notebooks. **Lesson**:
  cross-notebook DAG + stale detection. Maps to our `bind cascade` +
  topological ordering primitive. Relevant when we scale to many interlinked
  canvas notebooks that reference each other's atom state.

### Extraction / markup

- **Google `langextract`** — https://github.com/google/langextract (Python)
  Structured extraction from text via LLM. We adopt only the `AnnotatedDocument`
  JSON format (extraction_class + char_interval + attributes), strip LLM path,
  implement pure-TS shadow-layer runtime. Wrapped in `src/langextract.ts`.

### Shell / automation

- **Google `zx`** — https://github.com/google/zx
  Node.js shell scripting with `$\`cmd\`` template literal + bundled fetch /
  chalk / globby / fs-extra. **Lesson**: thin JS wrapper over shell ops.
  Candidate as atom-op backend for external-tool invocations.

- **Scoop** — https://scoop.sh/ (+ https://github.com/ScoopInstaller/Scoop)
  Windows CLI installer. Flat JSON manifests per package, buckets as
  git-versioned folders of manifests, executable install hooks. **Lesson**:
  flat-JSON registry + hook runner + git backing can back a generic atom
  store. Local buckets mean opt-in zero-infrastructure usage.

### Query / transformation

- **jid** — https://github.com/simeji/jid
  Interactive JSON navigator with real-time filter + autocompletion. **Lesson**:
  incremental drill-down UI pattern for exploring atom state.

- **JSONata** — https://jsonata.org/
  Declarative JSON query and transformation language. **Lesson**: reserved for
  M:N / relational queries over atoms; not needed for 1:1 extractor lambdas
  (per agreement in this thread).

### Data tooling as projection pattern

- **IntelliJ Database plugin** — `com.intellij.database/data/{extractors,
  aggregators, schema, schema.layouts}/*.groovy`
  Named projections catalog surfaced via right-click menu. Our extractors
  implementation mirrors this directly; identity projections ("Copy as...")
  mirror the Copy submenu (Absolute Path / File Name / Toolbox URL).

### Jupyter ecosystem

- **JupyterLab** — https://jupyterlab.readthedocs.io/
  Strategic position: Jupyter is a **production-tested superset** of much
  of what this architecture targets. Pattern harvesting approach: check
  JupyterLab extensions registry before implementing new features.

- **jupyterlab-contrib/jupyterlab-browser-storage** —
  https://github.com/jupyterlab-contrib/jupyterlab-browser-storage
  Client-side persistence of notebook state (IndexedDB / localStorage).
  **Lesson**: OPFS-adjacent pattern for "storage is projection" — notebooks
  persistable without server. Relevant when our canvas notebook needs
  durability.

- **IPython display protocol** (`_repr_html_`, `_repr_mimebundle_`, …)
  Per-object multi-MIME representation negotiation. Our identity projections
  catalog (`mimebundle` projection in `extractors.ts`) is wire-compatible.
  **Lesson**: validation that same-atom-multi-representation pattern works
  at production scale.

- **Jupyter nbformat 4.5** — https://nbformat.readthedocs.io/
  Our Canvas Notebook uses `cell.metadata.atom.{pos,size,faces,widget}` —
  extra keys ignored by standard readers, enabling round-trip visibility from
  standard Jupyter + rich rendering in our viewer.

### Runtime / build

- **Vite** + **rolldown-vite** — https://vite.dev/ + https://rolldown.rs/
  Dev server + bundler. **Virtual modules** via plugin `resolveId` / `load`
  hooks = structural match for our Virtual Object projection (one-way
  projection target, not substrate). **Environments API** — isolation
  mechanism for L0 scope/policy boundaries.

- **unplugin** — https://unplugin.unjs.io/
  Universal plugin factory (Vite / Rollup / Webpack / Rspack / esbuild).
  Portability primitive for projection-layer plugins.

- **Lexical** — https://github.com/facebook/lexical
  Text canvas substrate. Architectural mapping preserved in
  `LEXICAL_ADOPT_PLAN.md`. Our core wraps `lexical` (no `@lexical/react`)
  for minimal surface.

- **un-ts/synckit** — https://github.com/un-ts/synckit
  Sync-looking async via worker boundary + Atomics + SharedArrayBuffer.
  Projection sync delivery primitive (replaces yjs for our
  single-writer-multi-reader pattern per prior agreement).

- **web-container (hari-mohan-choudhary)** —
  https://github.com/hari-mohan-choudhary/web-container
  Browser-side Monaco + esbuild-wasm + QuickJS + OPFS reference
  implementation. Harvestable patterns for shell/exec carrier.

### Editing / interop (deferred)

- **Facebook Lexical `@lexical/yjs`** — CRDT collab layer (Yjs-based). Not
  integrated; reserved for Phase 8+ only if multi-user editing becomes a
  requirement.

- **mockforge-recorder** — https://lib.rs/crates/mockforge-recorder
  Rust crate. HTTP record/replay + schema generation. Optional persistence
  sidecar per RUNTIME_STACK component 3.

---

**How to read this list**: each reference tagged with **Lesson** briefly
states the architectural takeaway. When revisiting a reference for
implementation, start with the Lesson — the rest of the doc context
frames *why* that lesson mattered for this architecture.
