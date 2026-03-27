# Atomic Event to Assembly Mapping v0.1

## Purpose

This document defines how the upper declarative event DSL maps into the existing Assembly DSL layer.

The goal is:

- keep `emit/on` as the human/model-facing layer
- keep Assembly DSL as the explicit executable layer
- avoid inventing a second runtime

## Layer relation

The intended stack is:

1. `Declarative Event DSL`
2. `Assembly DSL`
3. runtime / worker calls / checkpoints

Meaning:

- users and models write `emit/on`
- system compiles it into assembly instructions
- assembly interpreter executes the explicit low-level plan

## Core mapping idea

`emit(...)` maps to:

- object/data materialization
- default application
- field assignment
- checks
- optional message write

`on(...)` maps to:

- post-event binding
- response parsing
- checks
- optional projections and emitted artifacts

At MVP stage, `on(..., "response", ...)` may compile as a deterministic post-`GEN` tail instead of a full async listener model.

## Why this is acceptable

For the first implementation, a `generate` batch is still mostly linear:

- build request
- call worker
- bind response

So the event syntax is mostly a semantic wrapper over a known linear expansion.

Later, the same syntax may gain true async runtime behavior.

## High-level mapping table

| Declarative Event DSL | Assembly DSL |
|---|---|
| `emit("task.input", { data: { text: ... } })` | `MOV` into local state / `PUT` into message |
| `schema` | field template / compile-time expansion |
| `defaults` | `MOV` from defaults into fields |
| `data` | `MOV` assignments |
| `checks: ["complete"]` | `CALL @ok, check_complete, ...` or equivalent |
| `call generate` semantics | `GEN` |
| `bind: "generate.response"` | `MOV`/`CALL` into response object fields |
| `project: ["response.table"]` | `CALL`/`PARSE` projection steps |

## Important note about schemas

Schemas do not need to exist as assembly opcodes.

They can remain compile-time structures used by the upper layer compiler.

So:

- upper layer reads `schema` and `defaults`
- compiler expands them into explicit assembly assignments/checks
- assembly stays small and stable

## Canonical example

### Upper declarative DSL

```js
emit("task.input", {
  data: {
    text: "написать 4 описания внешности демониц..."
  }
})

emit("generate.request", {
  schema: "native_generate_request",
  defaults: "native_generate_defaults",
  data: {
    prompt: @task.input.text,
    model: "local-model",
    max_length: 512
  },
  checks: ["complete"]
})

on("generate.request", "response", {
  bind: "generate.response",
  schema: "native_generate_response",
  checks: ["complete"]
})
```

### Assembly expansion

```asm
MOV  @task.input.text, "написать 4 описания внешности демониц..."

MOV  @generate.request.prompt, ""
MOV  @generate.request.temperature, 0.2
MOV  @generate.request.max_length, null
MOV  @generate.request.model, null

MOV  @generate.request.prompt, @task.input.text
MOV  @generate.request.model, "local-model"
MOV  @generate.request.max_length, 512

CALL @generate.request.check, check_complete, @generate.request, schema:"native_generate_request"
GEN  @generate.call.raw, @generate.request.prompt, worker:generator, temp:0.2, max:512
CALL @generate.response, bind_native_generate_response, @generate.call.raw
CALL @generate.response.check, check_complete, @generate.response, schema:"native_generate_response"
```

## Notes on the example

The exact helper functions may vary.

What matters is the expansion shape:

- defaults become explicit assignments
- data fields become explicit assignments
- check is explicit
- `GEN` is the worker syscall
- response binding is explicit

## `emit(task.input)` mapping

This is the simplest case.

Upper layer:

```js
emit("task.input", {
  data: {
    text: "..."
  }
})
```

Assembly:

```asm
MOV  @task.input.text, "..."
```

If the runtime also wants a visible message artifact, this may expand further:

```asm
MOV  @task.input.msg, "session"
PUT  @task.input.msg, user, @task.input.text
```

## `emit(generate.request)` mapping

This maps to three phases:

1. defaults
2. explicit data writes
3. checks

Example:

```asm
MOV  @generate.request.prompt, ""
MOV  @generate.request.temperature, 0.2
MOV  @generate.request.max_length, null
MOV  @generate.request.model, null

MOV  @generate.request.prompt, @task.input.text
MOV  @generate.request.model, "local-model"
MOV  @generate.request.max_length, 256

CALL @generate.request.check, check_complete, @generate.request, schema:"native_generate_request"
```

## `on(..., "response", ...)` mapping

At MVP stage:

```js
on("generate.request", "response", {
  bind: "generate.response",
  schema: "native_generate_response",
  checks: ["complete"],
  emit: ["response.output_message"],
  project: ["response.table"]
})
```

may compile into a linear tail:

```asm
CALL @generate.response, bind_native_generate_response, @generate.call.raw
CALL @generate.response.check, check_complete, @generate.response, schema:"native_generate_response"
CALL @response.output_message, emit_output_message, @generate.response
CALL @response.table, build_table_from_text, @generate.response.raw_text
```

This is enough for the first implementation.

## What needs helper functions

Some parts map directly to existing assembly opcodes.

Some parts are better handled as helper calls:

- `check_complete`
- `bind_native_generate_response`
- `emit_output_message`
- `build_table_from_text`

That is fine.

Assembly DSL already supports `CALL`, so these can exist as Python-backed assembly functions.

## What does not need to be in assembly

Do not push too much upper-level meaning into assembly syntax.

Assembly should stay:

- flat
- small
- explicit

Meaning:

- `schema` stays compile-time metadata
- `defaults` may expand before execution
- event semantics may compile to linear steps where appropriate

## Suggested first compiler target

The first target should only support:

- `emit(..., {data})`
- `emit(..., {schema, defaults, data, checks})`
- `on(..., "response", {bind, schema, checks})`

That is enough to cover the first generate batches.

## Short summary

The upper `emit/on` DSL should compile into the existing Assembly DSL.

For the first version:

- `emit` expands into assignments/defaults/checks
- `on(response)` expands into a post-`GEN` binding tail

This keeps the upper layer friendly while reusing the explicit lower layer already present in the project.
