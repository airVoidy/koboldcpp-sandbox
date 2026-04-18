# Session T Snapshot — Runtime Sandbox Nodes (TS) + jupyter_layer (Python)

> **For next-session pickup.** Self-contained: read this file + the plan file and you have full context.
> Worktree: `C:\llm\KoboldCPP agentic sandbox\.claude\worktrees\tender-archimedes`
> Plan: `C:\Users\vAiry\.claude\plans\wild-forging-melody.md`
> Branch: `master` @ `2438c775`
> Date: 2026-04-18

---

## 1. TL;DR

Built a **client-side Runtime Sandbox** in TypeScript that mirrors the **Python jupyter_layer** architecture (discovered on `demo/jupyter-on-master` branch). Both implementations share the same invariants: L0 = IDs + types, values strictly lazy, panels/virtual-objects with scope hierarchies, metadata-only persistence. The TS side ships Data Layer (FieldOp log + Store + signals), Runtime Object Layer (pluggable adapters: virtual, signal, vfs), Middlelayer (exec interceptor with shadow metadata), BashTerminal (xterm + just-bash in browser), and a TypeHierarchy debug panel. Live in browser via Vite @ port 5176. Next: tag-list pattern + atomic-DSL canonical syntax + remove Effect-union / HANDLERS legacy + JupyterAdapter to bridge TS ↔ Python.

---

## 2. Architecture Map (3 layers + syntax)

```
┌─────────────────────────────────────────────────────────────────┐
│  SYNTAX LAYER (syntax projections of one canonical form)       │
│    atomic-DSL:  msg_1.reactions[].exec <- :thumbsup: /cmd <- react│
│    postfix:     /react :thumbsup: msg_1.reactions[]              │
│    infix:       /call msg_1.reactions[] -> react :thumbsup:      │
│    template:    msg.reactions as exec.cmd >                      │
│                     msg_1 :thumbsup:                             │
│    JSON:        { msg_1: { reactions: { $post: ':thumbsup:' }}} │
│    loop:        for every $item in ...children[] do ...          │
│                                                                  │
│    All parse → AtomicPayload (canonical) → unfold → FieldOp[]   │
└─────────────────────────────────────────────────────────────────┘
                            │
┌─────────────────────────────────────────────────────────────────┐
│  RUNTIME OBJECT LAYER (adapters per runtimeType)                │
│    RuntimeAdapter<B>: { create, read, apply, subscribe,         │
│                         serialize, hydrate }                     │
│                                                                  │
│    virtual   — delegates to Store (baseline)        ✅          │
│    signal    — in-memory reactive                   ✅          │
│    vfs       — just-bash InMemoryFs                 ✅          │
│    replicache— server-authoritative + rebase        📋           │
│    lexical   — rich text editor backing             📋           │
│    quickjs   — isolated worker sandbox              📋           │
│    crdt      — SyncKit Fugue/Peritext               📋           │
│    jupyter   — Python jupyter_layer bridge          📋 NEW       │
│                                                                  │
│    Middlelayer: intercepts exec, captures prev/new state,       │
│                 writes _exec.<callId>.* shadow metadata          │
└─────────────────────────────────────────────────────────────────┘
                            │
┌─────────────────────────────────────────────────────────────────┐
│  DATA LAYER (one primitive)                                     │
│    FieldOp { seq, writer, ts, objectId, fieldName,              │
│              op: 'set'|'unset'|'retype'|'append', type, content }│
│                                                                  │
│    Store: op log + derived VirtualObject registry +             │
│           per-object version signals + registered projections   │
│                                                                  │
│    Signal micro-lib (~100 LOC): state/event/computed/effect     │
│    Lazy resolver: collectMissingRefs + resolveMissing           │
│                    (virtual object as self-describing query)    │
└─────────────────────────────────────────────────────────────────┘
```

---

## 3. Eight Architectural Principles (agreed this session)

1. **Two server endpoints only**: `/pchat/exec` + `/pchat/batch`. Library sync (Replicache push/pull, CRDT merge, VFS fetch) rides as named CMDs through exec. No new REST endpoints.

2. **Atomic payload = one wire format**: both declarative data (`{msg: {content: 'hi'}}`) and imperative markers (`{$toggle_user: 'alice'}`) live in same JSON shape. Unfolds at apply.

3. **Virtual-first, not table-first**: virtual objects are the primitive; atomic-path flat-table is ONE projection among many. Projections switch wholesale (not field-by-field).

4. **Lazy resolver = self-describing query**: object structure IS the query. Missing refs auto-fetched via `useLazyObject`.

5. **Polymorphism by naming, not APIs**: `runtimeType` tag selects adapter, same `RuntimeAdapter<B>` interface for all backends.

6. **Template declares, runtime follows**: `schema.json.runtimeType` inherited through chain; no hardcoded dispatches in TS.

7. **"Can be read from any point"**: syntax is reorderable. Same operation via atomic-DSL / postfix / infix / template-first / JSON / loop-for-every — all compile to same FieldOp batch.

8. **Name-scope parsimony**: virtual objects use **relative** names / schema references / generated ids. Only core primitives get absolute names (`card`, `cards`, `msg`, `channel`, `FieldOp`, `VirtualObject`, `ProjectionSpec`). Prevents name-pollution as runtime grows.

---

## 4. Key Conversation Quotes (architectural intent)

User statements that frame the work — refer back to these when in doubt:

- *"общие sandbox ноды с виртуализацией для агентов и людей, поэтому можно инстанцировать worktree (по сети), и синкать их через backend в риалтайме поконтейнерно"* — P2P mesh with virtualized sandbox per-container sync.

- *"exec, это уже не совсем l0, это l1: как раз сендбокс леер уже. предлагаю начать с exec-scope, где exec: это shell object со своим jsonl логом, разрешёнными командами, любой data"* — exec-scope = L1 primitive.

- *"всё равно так-то нужно возвращать на exec не полное зарезолвленное дерево, а apply_patch конкретно над тем, что изменилось. один респонс-один ответ"* — exec responses = diffs, not full state.

- *"нужна возможность после exec (это желательно на мидпоинте делать, и все exec роатить через ~балансер/локал sandbox, который может дополнительные трансформации сделать на промежуточным слоем над payloadom)"* — middlelayer intercepts all exec for prev/new state capture.

- *"можно даже инвариант объявить, что transform (тут не projection, один раз нужно вычислить для всей fs структуры по темплейту), -> (canonical path prefix); name -> (hashed id); type"* — slot descriptors as compile-time transform.

- *"виртуальные объекты, кстати, лучше не называть именами. достаточно то, что они в рантайме крутятся как схема -> на них уже можно сослаться/сгенерить имя"* — name-scope parsimony principle.

- *"создать на каждый тип проекций по виртуальному списку и докидывать туда объекты; а в объектах, в свою очередь, уметь резолвить соответствующую проекцию для объектов. что-то типа тегов"* — tag-list pattern simplification (preferred over bundle).

- *"её можно читать с любой точки!"* (about syntax form) — syntax-as-projection concept.

---

## 5. Live Code — `koboldcpp-sandbox/src/`

### Data Layer (`src/data/`) ✅ COMPLETE

| File | Purpose |
|------|---------|
| `types.ts` | `FieldOp`, `Field`, `VirtualObject`, `ProjectionSpec`, `VirtualList`, `Cookie` |
| `signal.ts` | Signal micro-lib (~100 LOC): `state`, `event`, `computed`, `effect` with auto-tracked deps stack |
| `store.ts` | `Store` class: op log + registry + signals + projections; `applyBatch`, `snapshot`, `subscribe`, `makeOp`, `toJSONL`, `fromJSONL` |
| `lazy.ts` | `collectMissingRefs`, `resolveMissing`, `ingestQueryNode` — self-describing query for dangling refs |
| `index.ts` | Singleton `getStore()`, `ingestChatState`, exposes `window.__store` |

### Runtime Object Layer (`src/runtime/`) ✅ PARTIAL (4/8 adapters)

| File | Purpose |
|------|---------|
| `types.ts` | `RuntimeType` union, `RuntimeObject`, `RuntimeAdapter<B>`, `BranchMeta`, `RuntimeTemplateSchema` |
| `layer.ts` | `RuntimeLayer`: adapter router, inheritance walker (`resolveRuntimeType`), instantiation, subscribe fan-out |
| `middlelayer.ts` | `Middlelayer`: before/after hooks, `exec()` method, prev/new state snapshots, `_exec.<callId>.*` shadow metadata writer, call log |
| `adapters/virtual.ts` | VirtualAdapter — delegates to Store, idempotent on existing ops |
| `adapters/signal.ts` | SignalAdapter — in-memory reactive via signal micro-lib |
| `adapters/vfs.ts` | VfsAdapter — file-backed via just-bash InMemoryFs, writes `meta.json`, `fields.json`, `ops.jsonl` per object |
| `index.ts` | Singleton `getRuntime()`, `instantiateAllFromStore()`, exposes `window.__runtime` |

### UI (`src/components/`, `src/hooks/`)

| File | Purpose |
|------|---------|
| `components/TypeHierarchy.tsx` | Tree grouped by virtualType / runtimeType / path, inline field inspector |
| `components/BashTerminal.tsx` | xterm + just-bash shell, line buffer, history, middlelayer audit hook |
| `components/DebugConsole.tsx` | Floating panel; tabs: L0 Log, Type Hierarchy, Bash |
| `hooks/useStore.ts` | `useStore`, `useVirtualObject(id)`, `useProjection(id, name)`, `useObjectsByType`, `useLazyObject(id, user)` via useSyncExternalStore |
| `hooks/useChat.ts` | Chat actions (unchanged API); calls `ingestChatState` on refresh |

### Build (`koboldcpp-sandbox/`)

- `vite.config.ts` — `nodePolyfills(zlib,buffer,util)` FIRST, `react()` SECOND, `esbuild.jsx='automatic'` safety net
- Deps: `just-bash`, `@xterm/xterm`, `@xterm/addon-fit`, `@xterm/addon-web-links`, `vite-plugin-node-polyfills`, `ahooks`, `jsonata`, `react`, `react-dom`, `@tanstack/react-query`

---

## 6. jupyter_layer — Python Twin (on `demo/jupyter-on-master`)

**Commits on top of master**:
- `fca4c674` (Apr 18, 07:51) — Add jupyter_layer: thin Panel>Object layer over Jupyter kernels
- `9bbf2cfc` (Apr 18, 09:28) — Add jupyter_layer demo: quest_order_case preprocessing

**Architecture parallel** (1-to-1 mapping):

| jupyter_layer (Python)         | our Runtime Layer (TS)                   |
|--------------------------------|------------------------------------------|
| `KernelSession` (ZMQ wrapper)  | `BashTerminal` / future `BashAdapter`   |
| `JupyterScope` — L0 view       | `Store` — op log + signals              |
| `scope.list_ids()`             | `store.all().map(o => o.id)`           |
| `scope.list_typed()`           | slot descriptors `{hash, type, path}`   |
| `scope.fetch(name)`            | `useLazyObject(id)` + `resolveMissing` |
| `Panel` named container        | `VirtualObject` scope                   |
| `JupyterObject` lazy accessor  | `VirtualObject` instance                |
| `panel.sync_from_scope()`      | `ingestChatState` + `instantiateAllFromStore` |
| `panel.sub_panel(name)`        | nested VirtualList / tag-list           |
| `LocalStore` (JSON per panel)  | FS sync + `runtime/containers/`         |
| `invalidate()`                 | signal version bump                     |

**Shared invariants** (both implementations enforce):
1. L0 = IDs + types only, no values eagerly
2. Values strictly lazy — cached on first access
3. Panel scoped, not global (name-scope parsimony)
4. Store holds only metadata — values stay in native backend (kernel / adapter)
5. Panel can be standalone (virtual vs baked)

**Files on `demo/jupyter-on-master`** (1068 lines total):
```
src/jupyter_layer/
  __init__.py     — public API (23 lines)
  kernel.py       — KernelSession ZMQ wrapper (110 lines)
  scope.py        — JupyterScope L0 view (92 lines)
  panel.py        — Panel + JupyterObject (170 lines)
  store.py        — LocalStore JSON persistence (97 lines)
  README.md       — architecture docs (in Russian)
examples/
  jupyter_layer_example.py        — mocked kernel example
  jupyter_demo_quest_case.py      — live NLP demo
tests/
  test_jupyter_layer.py           — 25 unit tests (mocked)
pyproject.toml                    — +deps: jupyter_client, ipykernel
```

**Integration decision for next session**: merge `demo/jupyter-on-master` → `master` (architectures align, no source conflicts — jupyter_layer adds only new files under `src/jupyter_layer/`). Then create `JupyterAdapter` in TS that bridges to Python jupyter_layer via server-side endpoint.

---

## 7. Next Session Priorities (in order)

### P0: Merge decision on `demo/jupyter-on-master`

- Inspect branch: `git log demo/jupyter-on-master --not master --oneline`
- Expected: 2 commits, all new files under `src/jupyter_layer/`, no conflicts
- Action: merge into master OR keep branched until `JupyterAdapter` bridge ready

### P1: Tag-list + Atomic-DSL canonical (simplification pass)

Removes `MessageEffect.kind` discriminated union + `HANDLERS` registry, replaces with one walker + lambda resolvers.

Files to create:
```
src/data/virtual-list.ts       — VirtualList as tag; addMember/removeMember/listsContaining
src/runtime/unfold.ts          — AtomicPayload → FieldOp[] walker with $lambda resolvers
                                 ($set $unset $post $remove $toggle $incr $append $merge $ref $proj $cmd)
src/runtime/syntax/atomic.ts   — parse/render atomic-DSL "target <- arg /tag <- method"
src/runtime/syntax/dispatch.ts — detect form, route to appropriate parser
```

Files to delete/simplify:
- `MessageEffect` discriminated union in `types/message.ts`
- Per-cmd `HANDLERS` registry in `handlers.ts`
- `useChat` named actions → all use atomic payloads via `exec({payload})`

### P2: Remaining syntax forms

- `parse-postfix.ts` — `/verb arg target`
- `parse-infix.ts` — `/call target -> verb args`
- `parse-template.ts` — `X as Y > \n body body`
- `parse-loop.ts` — `for every $x in Y do ...`
- `parse-json.ts` — direct JSON payload
- Round-trip tests: `parse(render(g)) === g` for every style

### P3: /call unified + container schema methods

- Extend template schema: `container_schema.methods: ['post', 'remove', 'toggle', ...]`
- `/call target -> method args` dispatches via type system (not TS code)
- First working example: `reactions` as container type with methods

### P4: Remaining adapters

- **1c.vii** — `JupyterAdapter` (new priority) — RuntimeType='jupyter', HTTP/WS bridge to server-side jupyter_layer
- **1c.iii** — `ReplicacheAdapter` — protocol-only, routes through `/pchat/exec` as `/sync push/pull/ack`
- **1c.iv** — `LexicalAdapter` — rich editor backing (install `lexical`, `@lexical/react`)
- **1c.v** — `QuickjsAdapter` — isolated worker via just-bash `DefenseInDepthBox`
- **1c.vi** — `CrdtAdapter` — SyncKit Fugue/Peritext or Yjs fallback

### P5: FS sync (Phase 1d)

- `fs-sync.ts` — git-branch-per-instance: branchForInstance, pushOpsToBranch, checkpointMerge
- `branchPolicy` from template controls: auto / manual / disabled
- Client-side via `isomorphic-git` OR server-side git endpoint

### P6: UI improvements

- Wire `useLazyObject` into `MessageList` for scroll-based lazy fetch
- Rewrite `FSView.tsx` via `useVirtualObject` (replace ChatState paths)
- Exec history projection — timeline view using `_exec.<callId>.*` shadow metadata

---

## 8. File Map After All Phases Complete

```
koboldcpp-sandbox/src/
├── data/
│   ├── types.ts              ✅ FieldOp, Field, VirtualObject, ProjectionSpec, VirtualList
│   ├── signal.ts             ✅ state/event/computed/effect
│   ├── store.ts              ✅ op log + registry + signals
│   ├── lazy.ts               ✅ missing-ref auto-fetch
│   ├── virtual-list.ts       📋 tag-list pattern (P1)
│   └── index.ts              ✅ singleton + ingest
│
├── runtime/
│   ├── types.ts              ✅ RuntimeObject, RuntimeAdapter, RuntimeType
│   ├── layer.ts              ✅ router + inheritance
│   ├── middlelayer.ts        ✅ exec interceptor + shadow metadata
│   ├── unfold.ts             📋 AtomicPayload walker + lambda resolvers (P1)
│   ├── syntax/
│   │   ├── dispatch.ts       📋 form detection + routing (P1)
│   │   ├── atomic.ts         📋 canonical atomic-DSL (P1)
│   │   ├── template.ts       📋 template-first form (P2)
│   │   ├── postfix.ts        📋 /op arg target (P2)
│   │   ├── infix.ts          📋 /call target -> m args (P2)
│   │   ├── json.ts           📋 JSON payload (P2)
│   │   └── loop.ts           📋 for-every-do expansion (P2)
│   ├── adapters/
│   │   ├── virtual.ts        ✅
│   │   ├── signal.ts         ✅
│   │   ├── vfs.ts            ✅
│   │   ├── jupyter.ts        📋 Python jupyter_layer bridge (P4 — NEW)
│   │   ├── replicache.ts     📋 (P4)
│   │   ├── lexical.ts        📋 (P4)
│   │   ├── crdt.ts           📋 (P4)
│   │   └── quickjs.ts        📋 (P4)
│   ├── fs-sync.ts            📋 (P5)
│   └── index.ts              ✅ singleton
│
├── components/
│   ├── TypeHierarchy.tsx     ✅
│   ├── BashTerminal.tsx      ✅
│   ├── DebugConsole.tsx      ✅
│   ├── MessageList.tsx       🔧 wire useLazyObject (P6)
│   └── FSView.tsx            🔧 rewrite via useVirtualObject (P6)
│
└── hooks/
    ├── useStore.ts           ✅
    ├── useChat.ts            ✅ (ingestion path added)
    └── useFieldStore.ts      🔧 adapt to tag-list (P1)
```

Legend: ✅ done, 📋 next, 🔧 refactor

---

## 9. Dev Setup (verified working)

```bash
# Install (already done)
cd koboldcpp-sandbox
npm install

# Start dev server (Vite on port 5176 via .claude/launch.json)
npm run dev

# Or via preview tool: start "tsx-dev" launch config
```

**Open** `http://localhost:5176` → chat UI appears.
**Debug** via `Ctrl+Shift+D` → 3 tabs (L0 Log, Type Hierarchy, Bash).
**Console**:
```js
window.__store     // Data Layer op log + registry
window.__runtime   // Runtime Object Layer (adapters + objects)
window.__middlelayer // Middlelayer call log
```

Server expected at `http://localhost:5002` (original Python pipeline-chat). Vite proxies `/api/*` to it.

---

## 10. Git / Branch Topology

```
origin/master                @ 2438c775  ← current work
origin/runtime-jsonata-slice @ 2438c775  ← identical backup (can delete)
origin/demo/jupyter-on-master @ 9bbf2cfc ← master + 2 jupyter_layer commits

Worktree (tender-archimedes) currently ON master @ 2438c775
```

**Commit chain on master**:
```
2438c775  Middlelayer + BashTerminal: exec audit + browser shell via xterm/just-bash
db57b6a1  Lazy resolver: virtual object as self-describing query for missing data
7b0ee1e0  TypeHierarchy debug panel: group by virtualType / runtimeType / path
89f12db9  VfsAdapter (Phase 1c.ii): file-backed via just-bash
ad2d279f  SignalAdapter (Phase 1c.i): local reactive backend
c32e82d6  Runtime Object Layer: skeleton + VirtualAdapter (Phase 1b)
1f56ba46  Data Layer foundations: FieldOp log + Store + signals
fb3d8d75  TSX cleanup: exec-only, remove Projection/Materialize legacy
```

**Note**: previous master HEAD was at `3bdb17a6` (with codex/runtime-unify-view work). Force-pushed past it. Those commits are preserved by SHA in git reflog and can be cherry-picked if specific fixes needed — see commits `943484f0`, `b8dc9f59`, `da25554b`, `57c3307d`, `98e415a5`.

---

## 11. Key Insights from This Session

### Insight 1 — Syntax as Projection (meta-level)

Just as data has projections (raw, serialize, atomic_root, obj_to_obj), **syntax itself has projections**. Same underlying Command Graph can be rendered as atomic-DSL / postfix / infix / template / JSON / loop-expansion. All parse → one canonical AtomicPayload. This means: syntax parsers are themselves projections, and Command Graph = VirtualObject (recursive application of same primitives).

### Insight 2 — "Virtual object is self-describing query"

Object structure dictates what to fetch when refs are dangling. Walk `fields`, collect `ref`/`path_abs`/`placeholder` targets not in Store, batch `/query` them, ingest responses as FieldOps **at the exact atomic path** where NULL was. No separate query builder. Object IS the query.

### Insight 3 — Middlelayer is the missing piece

Before this session: client called `api.exec()` directly; no history, no prev/new state, no audit. After: **every exec routes through `Middlelayer.exec()`** which captures prev state, sends, applies returned diff, writes shadow metadata `_exec.<callId>.{cmd,requester,ts,prev}` alongside each mutated path. Same path holds state-of-truth AND exec history, separated only by projection (`current_value` vs `exec_history`).

### Insight 4 — Horizontal virtual types → simplified to tag-lists

First proposed: bundle pattern `[msg_1, reactions_1]` as horizontal VirtualType wrapping two sibling objects. User then simplified to: **tag-list pattern** — each projection type = a virtual list, objects belong to N lists simultaneously, each list knows its projection. Uses existing `VirtualList` primitive, no specialized Bundle type needed.

### Insight 5 — Atomic-DSL is closest to runtime semantics

```
msg_1.reactions[].exec <- :thumbsup: /cmd <- react
```
- `[]` = list-scope invariant (architectural primitive)
- `.exec` = real field (exec queue)
- `<-` = append/write
- `/tag` = constructor (`/cmd`, `/val`, `/ref`, `/proj`, `/call`) — type signal for decomposer

No sugar. Direct mapping to FieldOp append on the `.exec` field. Other syntax forms (postfix, infix, etc.) abstract away runtime structure; atomic-DSL exposes it.

### Insight 6 — Python twin confirms architecture

`jupyter_layer` discovered on `demo/jupyter-on-master` implements same Panel > Object pattern in Python over Jupyter kernels. 1068 lines, 25 tests, real NLP demo. This **validates** our architecture independently and provides a ready backend for `RuntimeType: 'jupyter'` adapter.

---

## 12. Open Questions for Next Session

1. **Merge `demo/jupyter-on-master`?** Likely yes — no conflicts expected. Decide at session start.

2. **What exactly does `.exec[].init` do on a bundle?** When a new virtual type instance is created, the `init` command inside its own exec queue bootstraps it — but the current implementation doesn't yet have first-class init semantics. Design at P1.

3. **Where do lambda resolvers live?** In `unfold.ts` as a registry, or as pluggable per virtualType via template? Probably both: core primitives (`$set $toggle $incr`) hardcoded, custom ones registered per template.

4. **Slot descriptors format finalization**: `{hash, type, path}` discussed but not formally coded. When building lazy lists, is `hash` the `seq`+`writer` tuple from FieldOp, or a content hash? Probably the former for cheap equality.

5. **Shell tunnel replacement for /pchat/exec**: architecturally `api.exec()` should eventually be a long-lived socket/ssh session, not HTTP-per-call. Needed when agent workflows run continuous bidirectional streams. Defer to Phase 2 after Phase 1 closes.

---

## 13. Opening Message for New Chat

Suggested first prompt:

> Continuing from `SESSION_T_SNAPSHOT.md` + `wild-forging-melody.md` plan.
> Worktree on `master` @ `2438c775`. Data + Runtime + Middlelayer + BashTerminal live in browser.
> Python jupyter_layer exists on `demo/jupyter-on-master` as architectural twin.
>
> First: review `demo/jupyter-on-master` — likely merge into master (no conflicts).
> Then: Priority 1 — tag-list pattern + atomic-DSL canonical syntax, which lets us remove `MessageEffect` union + `HANDLERS` registry and replace with one walker.

---

## Appendix: useful one-liners

```bash
# Branch status
git log --oneline --graph --all -20

# See what jupyter_layer adds
git log demo/jupyter-on-master --not master --stat

# Restart clean worktree state (throw runtime artifacts)
git checkout -- root/runtime/containers/ root/log.jsonl
rm -rf root/pchat

# Fresh Vite cache if plugin-order issues recur
rm -rf koboldcpp-sandbox/node_modules/.vite

# Type-check just TS
cd koboldcpp-sandbox && npx tsc --noEmit -p tsconfig.app.json
```
