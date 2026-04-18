# PChat Exec Runtime Architecture

## Status

This document defines the target architecture for the next `pipeline-chat` runtime.

It is intentionally stricter than the current codebase.

Primary goal:

- rebuild a minimal, explainable, deterministic runtime
- remove accidental coupling between client state, server state, runtime containers, git views, and UI helpers
- use this document as the source of truth for implementation

---

## Core Invariants

### 1. Single mutation boundary

All user-visible state changes go through:

- `exec()`
- optionally `exec_batch()`

Nothing else is allowed to mutate truth state.

That means:

- no direct UI patch endpoints in the main path
- no hidden mutation through `view`
- no client-side write helpers that bypass `exec`
- no domain-specific HTTP endpoints like `/post`, `/edit`, `/react`

### 2. One user action = one exec

For user actions:

- one click / one submit / one explicit action
- one `exec()`
- one log entry

Secondary reads may exist for boot, lazy resolve, or debug, but not as part of the canonical mutation path.

### 3. No duplicated truth values

Truth values are stored once.

Everywhere else:

- references
- projections
- aliases
- representations

No duplicated value caches should become semantic truth.

### 4. Server entities and client entities are different layers

Server objects:

- exec scopes
- refs
- runtime objects
- schema-driven handlers

Client objects:

- cards
- lists
- panels
- render containers

Client objects may depend on server objects, but must not become server truth.

### 5. Filesystem is a projection, not the semantic model

Physical storage should stay simple:

- flat or almost flat lists
- append-friendly logs
- deterministic rebuild

Hierarchy is mostly virtual.

---

## Layer Model

## L0: Router / Node Layer

L0 is structural, not semantic.

Responsibilities:

- scope boundaries
- policy boundaries
- routing
- relative addressing
- ownership / visibility
- local request/response placement

An L0 node is an `exec_scope`.

It may later host:

- policy files
- routing config
- local handlers
- links to sandbox/file storage

But the core unit is still:

- scope
- local log
- references

L0 does not need to expose one globally shared user log as semantic truth.

---

## L1: Exec Object Layer

This is the main `sandbox-server` interaction layer.

Every exec scope owns:

- local `exec` log
- baked methods
- scope-local data refs
- projections

Canonical request model:

- `exec(scope, method, args, user, log=true)`

Canonical response model:

- one response object
- placed into the same local scope

L1 is hierarchical, transport-oriented, and generic.

It must not be tightly coupled to chat semantics.

---

## L2: Runtime Object Layer

Truth is represented through atomic runtime objects.

Base storage model:

- atomic source fields
- stable refs
- deterministic reconstruction

The important rule:

- values are stored once
- everything else points at them

---

## L3: Virtual Object / Projection Layer

Virtual objects are assembled from runtime refs.

Projection is defined as:

- one virtual object -> another virtual object

Not:

- field copy
- value duplication
- table as truth

Virtual objects may represent:

- channel object
- message object
- message list object
- channel list object
- editor object
- render-ready card object

---

## L4: Client Render Layer

This layer contains:

- cards
- panels
- rows
- lists
- UI helper objects

These are client-facing shapes only.

They must remain:

- schema-driven
- replaceable
- disposable

They are never the canonical truth.

---

## Storage Model

## Physical Storage

Physical storage should be simple.

Preferred shape:

- flat or almost flat lists inside a parent node
- append-friendly logs
- deterministic scan order

Examples:

- request list
- response list
- child ref list
- object ref list

Physical storage should not try to preserve every semantic hierarchy.

That hierarchy is projected.

---

## Canonical Identity

Every truth field or truth object should have a stable ref identity.

Recommended basis:

- source payload ref
- relative path within payload

Do not duplicate the same truth field under multiple physical paths.

---

## Exec Scope Object

Base generic object:

- `exec_scope`

Minimal responsibilities:

- own local exec log
- own baked methods
- own local refs
- own local projections

Minimal conceptual shape:

```json
{
  "scope": "channel:test",
  "data": {},
  "methods": {},
  "projections": {},
  "meta": {}
}
```

Important:

- `data` stores refs or aliases, not semantic value copies
- `methods` are baked executable handlers
- `projections` are views over refs and logs

---

## Exec Log

Exec log is the replay log.

This is the canonical deterministic action stream.

Rule:

- one user action = one exec log entry

Low-level request/response traces may exist separately for diagnostics, but they are not the same thing as the user-level replay log.

---

## Runtime Truth Model

## Atomic Runtime Objects

The base truth unit should be projection-aware, but still atomic.

Conceptually:

- source payload ref
- relative path to field
- stable value ref
- template-relative path

Value itself is not duplicated into every projection.

---

## Ref Object

Everything should resolve through a single ref abstraction.

A ref can provide different read projections:

- value projection
- absolute path projection
- relative path projection
- template projection
- render projection

This means:

- one ref
- multiple representations
- one truth source

---

## Projection Model

Projection is not a field copy.

Projection is:

- `projection(ref_object, projection_name) -> projected_state`

The source object does not need to know all its projections.

The projection layer points to the source, not the other way around.

This is critical.

It keeps:

- source small
- projections replaceable
- different render modes possible

---

## Canonical Projection Names

Some projections should be treated as standard built-ins.

Examples:

- `absolute_path`
- `relative_path`
- `template_path`
- `value`
- `display`
- `editor`

This allows predictable generic tooling.

---

## Virtual Hierarchy

Hierarchy should mostly be virtual.

That means:

- one object may appear in several lists
- one object may appear in several trees
- one object may have one canonical projected path but multiple view paths

Examples:

- same message in:
  - channel messages
  - recent messages
  - unread messages
  - per-user messages
  - thread view

No duplication of truth object is needed for this.

---

## Template System

## Purpose

Templates define:

- allowed commands
- allowed projections
- local field layouts
- runtime views
- client-facing object shapes

Templates should be the main place for semantics.

The server core should remain generic.

---

## Template Commands

Template commands are the desired place for domain actions.

Examples:

- `add_channel`
- `select`
- `post`
- `react`
- `edit`
- `delete`

These should live in template command files, not in `server.py`, unless truly generic.

---

## Schema Ownership

If a schema says a command exists, its implementation should be discoverable through the template layer.

A partial migration is not acceptable as an endpoint architecture.

Specifically:

- schema-driven command declarations
- no hidden server-only semantic fallback

Otherwise the command resolution graph becomes impossible to reason about.

---

## Client Model

## Client Containers

Client containers are normal projections.

They are not special semantic truth holders.

They can represent:

- channel list panel
- message list panel
- message card
- reaction bar
- editor card

Each client container should declare:

- required fields
- placeholder slots
- render-oriented shape

But it must still resolve through refs.

---

## Placeholder Policy

Clientside should resolve values via placeholders.

That means:

- json payloads may contain hashed refs / placeholders
- actual value resolution happens via ref projection

This keeps:

- value single-sourced
- sync easier
- patch/update consistency intact

---

## Mutation Policy

## Edit / React / Delete

These are ordinary exec methods.

Even if they eventually use atomic patch internally, that must still happen behind the single exec boundary.

The user-facing path is:

- action
- one exec
- one response

Not:

- action
- exec
- atomic patch endpoint
- view/materialize endpoint
- redraw

---

## Materialize

Materialize is allowed only as an internal compile or resolve helper.

It is not allowed to be the main user mutation path.

Good uses:

- compile local projection graph
- non-persistent runtime resolve
- lazy render prep

Bad uses:

- required second user-action step
- hidden mutation path
- replacing canonical exec

---

## Git / Sandbox Model

Git-aware structure and sandbox-aware structure should be treated as projections over truth/runtime state, not as an accidental side effect of UI.

The current codebase mixed:

- raw git directory traversal
- runtime sandboxes
- chat projections
- UI materialization

The next architecture must separate them.

Recommended rule:

- raw `.git` is raw storage
- git tree view is a projection
- sandbox tree view is a projection

Neither should be confused with semantic chat truth.

---

## Minimal Next Build

The minimal clean rebuild should include:

1. generic `exec()` / `exec_batch()`
2. template-driven command resolution
3. `exec_scope` as the base object
4. atomic runtime refs as truth
5. virtual objects and projections over refs
6. client containers as projection-only render shapes
7. zero domain-specific mutation endpoints
8. zero required `view/materialize` calls in the action path

---

## Migration Rules

When rebuilding:

1. prefer generic core over server hardcode
2. prefer template commands over `cmd_*` domain handlers
3. prefer refs over copied values
4. prefer projections over stored derived trees
5. prefer one exec response over multi-step client orchestration

---

## Non-Goals

The next rebuild does not need to solve immediately:

- final sync layer
- final git projection UX
- final sandbox persistence policy
- final cleanup strategy for derived projections

These are secondary.

Primary task is to restore:

- explainability
- deterministic exec path
- clean layering

