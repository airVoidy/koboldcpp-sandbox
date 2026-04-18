# Lexical Adoption Plan

## Status

**Narrow scope**: this doc covers Lexical-specific mapping only.
Broader runtime stack (5 components, of which Lexical is one) lives in
`RUNTIME_STACK.md` in this same directory. Read that first.

Lexical's role in the stack: **text canvas / editor**, one of five components.
Not the substrate for everything — only for text content editing.

`un-ts/synckit` is NOT a Lexical-specific bridge: it is the projection sync +
worker bridge primitive for the entire stack, used by all five components.
It replaces yjs for our single-writer-multi-reader projection model.

---

## Why Lexical

Independent derivation during architecture discussion converged on the same structural
invariants Lexical already implements in production (3M weekly downloads, Meta-maintained).
Rebuilding these from scratch would duplicate battle-tested infrastructure without gain.

Adoption criteria met:
- Event-sourced state (EditorState + command dispatch)
- Immutable substrate with controlled mutation (double-buffered updates)
- Auto-cascading transforms (our bind semantics)
- Priority-based handler resolution (our template command dispatch)
- Native replay via `@lexical/history` + `lexical-devtools`
- Headless server-side operation via `@lexical/headless`
- Extension-based domain ownership (matches our template-owns-domain rule)
- Typed command payloads (matches our `exec()` shape)

---

## Architectural mapping

| Our model | Lexical primitive |
|-----------|-------------------|
| SoT container, sealed after commit | `EditorState` frozen after reconciliation |
| `growing → sealed` lifecycle | Work-in-progress clone during `editor.update()`, frozen on commit |
| Accessor overload (`.value = X` routes through method) | `$` functions + `node.getWritable()` |
| Node identity stable across versions | Runtime-only key shared across logical node versions |
| Resolve cascade on SoT change | Node transforms — auto-fired during updates when nodes change |
| Bind as event subscription | `registerCommand`, `registerUpdateListener`, `registerNodeTransform` |
| Single mutation boundary (`exec()` / `exec_batch()`) | `dispatchCommand(command, payload)` + priority propagation |
| One user action = one log entry | One command dispatch = one history entry |
| Read-path projection (pure, single-step) | `editor.read(() => ...)` |
| Write-path resolve (cascading) | `editor.update(() => ...)` — double-buffered, batched |
| Templates own domain | Extensions: `defineExtension({build, config, nodes, register})` |
| Replay / undo-redo | `@lexical/history` + `lexical-devtools` play slider |
| Bake-time composition | Extension registration before editor creation |
| Headless runtime for server | `@lexical/headless` |

---

## What we add on top

Lexical provides the substrate. The following layers remain custom:

### L0 (Router / Node)
- Scope resolution (`channel:test`, `message:msg_1`)
- Policy boundaries for sandbox / FS capability
- Python-side routing between exec scopes
- Not an editor concern; lives in our server core

### Template command layer
- Domain commands (`add_channel`, `select`, `post`, `react`, `edit`, `delete`)
- Declared in `root/templates/{type}/commands/*.py`
- Each template command maps to a Lexical command registration in the client engine
- Server core stays generic; templates own semantics

### Coordination bridge (`un-ts/synckit`)
- Sync-looking calls from main thread (UI) / Python into worker-hosted Lexical
- Atomics + SharedArrayBuffer blocking
- `createSyncFn(workerPath)` wrapping exec dispatch
- Removes async plumbing from caller perspective while preserving isolation

### Storage projection
- Lexical EditorState JSON ↔ our FS-first storage (`_meta.json`, `_data.json`)
- Not Lexical's concern; serializer sits above its export format
- Git-aware persistence is a separate projection layer

### Multi-user CRDT (deferred)
- `@lexical/yjs` when / if multi-user editing becomes a requirement
- Orthogonal to single-user worker isolation via synckit
- Not required for Phase 1–5 per `IMPLEMENTATION_PLAN.md`

---

## What we do not customize

To keep the adoption clean and avoid fighting the framework:

- Lexical's node model (ElementNode, TextNode, DecoratorNode) — use as-is
- Command dispatch priority system — use as-is
- History (`@lexical/history`) — use as-is
- DevTools (`lexical-devtools`) — use as-is
- Extension API (`defineExtension`) — our templates register as extensions

---

## Phase alignment with `IMPLEMENTATION_PLAN.md`

### Phase 1 — Generic Core
- Initialize Lexical editor in headless mode (server) + regular mode (client)
- Wire `/pchat/exec` endpoint to `editor.dispatchCommand`
- Exec log = Lexical history stream (serialized)
- No chat-specific commands yet

### Phase 2 — Minimal Templates
- Each template command = Lexical command registered via extension
- `channels`, `channel`, `message` extensions
- Domain commands stay in Python templates; client dispatches to Lexical commands

### Phase 3 — Atomic Runtime Refs
- Lexical nodes carry our ref identity (runtime-only key + our stable payload ref)
- Bridge: node `__key` + our `payload_ref` pair in node state
- No value duplication — field accessors resolve through ref projection

### Phase 4 — Virtual Objects
- Virtual objects = Lexical nodes composed with projection extensions
- Message card, channel card — each a decorator node with field projections

### Phase 5 — Client Containers
- `@lexical/react` plugins for each container type
- Containers render through ref projection, never store truth

### Phase 6 — Git / Sandbox Projections
- Headless Lexical on server exports EditorState JSON → FS-first storage
- Git projection is a read-only view over that storage
- Sandbox worktree-per-instance from plan retains shape

---

## Dependencies to install

Deferred until implementation start (docs-first workflow):

```
lexical
@lexical/react
@lexical/history
@lexical/headless
@lexical/extension
@lexical/rich-text        # optional, for rich-text mode
synckit                    # un-ts/synckit, worker bridge
# @lexical/yjs + yjs       # deferred to Phase 6+ if multi-user needed
```

All MIT-licensed, published to npm, active maintenance.

---

## Risks

- **Lexical's EditorState ↔ our storage serializer mismatch** — need adapter layer; risk is low since EditorState is JSON-serializable by design
- **synckit requires COOP/COEP headers** for SharedArrayBuffer — dev server config needed, production deployment headers needed. Same constraint as OPFS usage in `runtime_refs/web-container/`, so infrastructure precedent exists
- **Extension API is newer than plugin API** — some examples use plugins (legacy); we standardize on extensions per AGENTS.md guidance
- **Python ↔ JS engine transport** — if using synckit bridge from Node layer, Python → Node needs separate channel (HTTP / stdio). Not Lexical's concern; solved at server layer

---

## Open questions

- Serialization format between Lexical EditorState and our FS storage — should it be direct JSON dump, or schema-transformed projection?
- Should headless Lexical run in a dedicated Node process, or embedded in the Python server via a subprocess call synced through synckit?
- How do template extensions get discovered from `root/templates/`? Scan + dynamic import, or explicit registry?

These resolve during Phase 1 implementation.
