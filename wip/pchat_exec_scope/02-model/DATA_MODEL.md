# PChat Data Model

## Scope

This document defines the target data model used by the new exec runtime.

It is intentionally generic.

Domain semantics should live in templates and projections, not in the server core.

---

## Base Units

## 1. ExecScope

Generic local execution boundary.

Responsibilities:

- local exec log
- local methods
- local refs
- local projections

Conceptual shape:

```json
{
  "scope": "channel:test",
  "data": {},
  "methods": {},
  "projections": {},
  "meta": {}
}
```

Rules:

- `data` stores refs or aliases
- methods are baked
- projections are derived

---

## 2. RefObject

Stable pointer to a truth object or truth field.

RefObject should be able to resolve different named projections.

Conceptual shape:

```json
{
  "kind": "ref",
  "id": "stable-ref-id",
  "source_ref": "payload-or-object-ref",
  "projection": {
    "default": "value"
  },
  "meta": {}
}
```

RefObject is the central abstraction.

Everything else should point to it.

---

## 3. Atomic Runtime Object

Atomic truth field representation.

This is not just `path -> value`.

It should carry enough structure to support:

- canonical identity
- template-relative location
- payload-relative location
- value resolution without duplication

Conceptual shape:

```json
{
  "kind": "atomic_runtime_object",
  "id": "hash-or-stable-id",
  "payload_ref": "source-object-ref",
  "relative_path": "data.content",
  "template_relative_path": "message.content",
  "value_ref": "value-ref",
  "meta": {
    "value_type": "str",
    "origin": "json_field"
  }
}
```

Important:

- do not duplicate raw value into every projected object
- value should be resolved through `value_ref` or an equivalent bind

---

## 4. Value Object

Optional separate storage for actual value payload.

Useful when:

- values are large
- values are reused
- values should stay fully single-sourced

Conceptual shape:

```json
{
  "kind": "value",
  "id": "value-id",
  "value": "hello",
  "meta": {
    "value_type": "str"
  }
}
```

---

## 5. Virtual Object

Projection-assembled object over refs.

Virtual objects are not truth.

They are local shapes built from refs.

Conceptual shape:

```json
{
  "kind": "virtual_object",
  "id": "message-card:msg_1",
  "schema": "message_card",
  "fields": {
    "content": {
      "ref": "ref-msg1-content",
      "projection": "display"
    },
    "user": {
      "ref": "ref-msg1-user",
      "projection": "value"
    }
  },
  "meta": {}
}
```

---

## 6. Virtual List

Ordered collection of refs or virtual objects.

Conceptual shape:

```json
{
  "kind": "virtual_list",
  "id": "channel:test/messages",
  "items": [
    { "ref": "message:msg_1" },
    { "ref": "message:msg_2" }
  ],
  "meta": {
    "order": "created_desc"
  }
}
```

Virtual list should never become truth storage for the objects it points to.

---

## Projection Model

Projection is always:

- `source object -> projected object`

Not:

- `value duplication`
- `table as truth`
- `field copy as storage`

Projections may expose standard representations:

- `value`
- `absolute_path`
- `relative_path`
- `template_path`
- `display`
- `editor`

---

## Placeholder Model

Client payloads should prefer placeholders or hashed refs over embedded values.

Conceptual field shape:

```json
{
  "ref": "ref-msg1-content",
  "projection": "display",
  "placeholder": "slot:0"
}
```

The placeholder is not a string template feature.

It is a structural slot in a projection schema.

---

## Canonical Path Policy

Canonical path should be a projection, not a duplicated storage string scattered everywhere.

It is acceptable to expose:

- `absolute_path` as a standard named projection

But the canonical identity should still come from:

- source payload ref
- relative path

---

## Object Examples

## Channel

Conceptually:

```json
{
  "kind": "exec_scope",
  "scope": "channel:test",
  "data": {
    "messages": [
      { "ref": "message:msg_1" },
      { "ref": "message:msg_2" }
    ]
  }
}
```

## Message

Conceptually:

```json
{
  "kind": "exec_scope",
  "scope": "message:msg_1",
  "data": {
    "content": { "ref": "ref-msg1-content" },
    "reactions": { "ref": "ref-msg1-reactions" }
  }
}
```

## Message Card

Conceptually:

```json
{
  "kind": "virtual_object",
  "schema": "message_card",
  "fields": {
    "content": { "ref": "ref-msg1-content", "projection": "display" },
    "reactions": { "ref": "ref-msg1-reactions", "projection": "display" }
  }
}
```

---

## Mutation Semantics

Edits do not mutate the client object directly.

They go through:

1. `exec`
2. server-side resolution
3. truth update
4. projection rebuild

This keeps:

- immutable or append-oriented truth
- clean replay
- coherent projection refresh

