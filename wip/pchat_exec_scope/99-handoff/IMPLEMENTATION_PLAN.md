# PChat Rebuild Plan

## Goal

Rebuild a minimal, explainable `pipeline-chat` runtime from scratch in a separate path.

Work from documentation first.

Do not reuse accidental coupling from the current implementation.

Stack composition lives in `RUNTIME_STACK.md`. This plan aligns build phases
with the 5-component stack.

---

## Phase 1: Generic Core

Implement only:

- generic `exec()`
- generic `exec_batch()`
- scope resolution
- template command resolution
- local exec log

No chat-specific methods in `server.py`.
No container-specific wiring yet (Lexical / web-container / synckit come in Phase 5).

Deliverable:

- generic runtime skeleton
- Python FastAPI with `/pchat/exec` and `/pchat/batch` endpoints
- exec log as append-only file

---

## Phase 2: Minimal Templates

Create minimal template types:

- `channels`
- `channel`
- `message`

Create minimal template commands:

- `add_channel`
- `select`
- `post`
- `react`
- `edit`
- `delete`

Live in `root/templates/{type}/commands/*.py`.

Deliverable:

- all domain commands live in templates
- template discovery and hot-reload
- zero chat-specific logic in server core

---

## Phase 3: Atomic Runtime Refs

Implement:

- atomic runtime object store
- value refs
- relative path refs
- basic projection names (`value`, `absolute_path`, `relative_path`, `template_path`, `display`, `editor`)

Deliverable:

- no value duplication in projections
- single source of truth for every field

---

## Phase 4: Virtual Objects

Implement:

- message virtual object
- channel virtual object
- message list virtual object
- channel list virtual object

Each as Lexical extension scaffold (see `LEXICAL_ADOPT_PLAN.md` for mapping).

Deliverable:

- object-to-object projections
- virtual objects assembled from refs, never duplicate truth

---

## Phase 5: Client Containers + Stack Wiring

Wire the 5-component runtime stack:

### Lexical integration
- Install: `lexical @lexical/react @lexical/history @lexical/headless @lexical/extension @lexical/rich-text`
- Wire template types as Lexical extensions
- Text content, messages, edit fields use Lexical containers
- `@lexical/headless` on server for EditorState generation

### Shell / exec container (web-container pattern)
- Use existing: `just-bash`, `@xterm/xterm`, `cmdk`
- Adapt from `wip/runtime_refs/web-container/`: 3-worker split (orchestration / compile / execute)
- Optional additions if we go full web-container: `quickjs-emscripten`, `esbuild-wasm`, `idb`, `@monaco-editor/react`

### synckit worker bridge
- Install: `synckit`
- Wire main thread ↔ Lexical worker and ↔ web-container worker
- Projection sync between components via synckit primitives
- Set COOP/COEP headers in Vite dev + production

### Client render containers
- React components as plain projections (sidebar, message list, message card)
- Never store truth; always resolve through refs

Deliverable:

- client layer separated from server truth
- working text + shell container composition
- cross-worker coordination without async plumbing leakage

---

## Phase 6: Shadow Markup + Persistence

### Shadow markup layer (langextract repurposed)
- Pure-TS implementation using langextract's `AnnotatedDocument` format
- No LLM dependency — agentless markup
- Shadow layers bind to char ranges, move with text, mutually unaware
- Lexical extension exposing the shadow layer as a projection
- Separate `SHADOW_LAYER.md` spec (to be written before Phase 6)

### Persistence via mockforge
- Install mockforge CLI as sidecar: `cargo install mockforge-cli`
- Runtime projection checkpoints dump to mockforge HTTP endpoints
- Session restore: replay from mockforge → state reconstitutes
- Schema auto-generated from captured request/response pairs

Deliverable:

- text content carries range-tied metadata via independent shadow layers
- sessions persist across restarts via mock replay
- schema for runtime objects derived from actual usage

---

## Phase 7: Git / Sandbox Projections

Only after the above is stable:

- git tree projection (read-only view over storage)
- sandbox tree projection (isolated worktree per instance)
- lazy sync helpers between components

Deliverable:

- git/sandbox stop polluting chat truth model
- clean projection semantics over underlying FS

---

## Phases 8+: Deferred concerns

Not part of the initial rebuild:

- Multi-user CRDT (only if/when shared editing required — would use `@lexical/yjs`;
  architecturally optional because synckit handles our single-writer pattern)
- Managed collab services (Liveblocks, Hocuspocus) — not aligned with local-first
- Cloud persistence — explicit opt-in, not default

---

## Rules During Rebuild

1. No new domain mutation endpoints
2. No required `view/materialize` in action path
3. No truth duplication
4. No client state as semantic truth
5. No domain logic hardcoded into server core
6. Docs-first: update relevant spec doc before implementation
7. Respect phase boundaries — don't pull Phase 5 wiring into Phase 1

---

## Cross-references

- `01-foundation/ARCHITECTURE.md` — architectural invariants and layer model
- `01-foundation/RUNTIME_STACK.md` — 5-component stack composition (read before Phase 5)
- `01-foundation/LEXICAL_ADOPT_PLAN.md` — Lexical-specific mapping reference
- `02-model/DATA_MODEL.md` — data primitives (ExecScope, RefObject, etc.)
- `03-runtime/COMMAND_MODEL.md` — exec / command resolution rules
- `99-handoff/HANDOFF.md` — fresh-thread starter guide
- `99-handoff/BRANCH_NOTES.md` — git branch reference map
