# PChat Command Model

## Goal

Define a generic command model for the new runtime.

The server core should know how to:

- parse exec requests
- resolve template commands
- execute them in scope
- append exec log

It should not know chat semantics directly.

---

## Canonical Entry Points

Allowed mutation entry points:

- `exec()`
- `exec_batch()`

No domain-specific mutation endpoints.

---

## Exec Request

Conceptual shape:

```json
{
  "scope": "channel:test",
  "cmd": "/post hello",
  "user": "anon",
  "log": true
}
```

---

## Exec Response

Conceptual shape:

```json
{
  "ok": true,
  "scope": "channel:test",
  "result": {},
  "effects": [],
  "projections": {}
}
```

The exact payload is implementation-dependent, but one user action should still correspond to one exec response.

---

## Resolution Order

Recommended resolution order:

1. resolve scope
2. resolve node type / template
3. resolve template command by inheritance
4. only then allow generic server-core fallback commands

Generic commands may include:

- `cd`
- `ls`
- `cat`
- `query`
- `rm`

Domain commands should live in templates.

---

## Template Commands

Template command files should expose:

```python
def execute(args, user, scope, ws):
    ...
```

Where:

- `scope` is the local exec scope
- `ws` is the generic workspace/runtime API

---

## Domain Commands

Examples that belong to templates:

- `add_channel`
- `select`
- `post`
- `react`
- `edit`
- `delete`

These are not server-core commands.

---

## Command Side Effects

Allowed:

- update truth objects
- append exec log
- rebuild local projections
- return projection-aware response

Not allowed:

- call separate hidden mutation endpoints from UI
- require `view` as second mutation step
- treat client cache as truth

---

## Logging

Every exec should append a canonical user-level action record.

Conceptual shape:

```json
{
  "cmd": "/react msg_1 👍",
  "user": "anon",
  "ts": "2026-04-16T00:00:00Z"
}
```

Transport-level tracing may exist separately if needed.

---

## Batch Semantics

`exec_batch()` is allowed, but it must still remain explicit.

Good use:

- macro execution
- scripted system operations
- coordinated non-user workflows

Bad use:

- hiding extra user mutation steps

---

## Client Contract

Client UI commands are thin wrappers over exec methods.

Examples:

- `post_message(fields...) -> exec("/post ...")`
- `react(fields...) -> exec("/react ...")`
- `edit_message(fields...) -> exec("/edit ...")`

Client should only pass fields.

Methods themselves are baked on the server/template side.

