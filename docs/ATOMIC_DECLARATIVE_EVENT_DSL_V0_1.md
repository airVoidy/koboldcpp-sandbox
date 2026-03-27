# Atomic Declarative Event DSL v0.1

## Purpose

This document defines a more model-friendly upper DSL layer for Atomic.

The goal is:

- stay close to semantics
- stay pleasant for humans
- stay easy for models to continue
- stay compatible with JSON, table, and message-based data

This layer is not the low-level assembly DSL.

It sits above it.

## Core idea

Use a declarative event-shaped syntax:

- `emit(...)`
- `on(...)`

This is easier to read than a procedural list of commands and closer to patterns already familiar to models.

## Minimal pattern

```js
emit("generate.request", {
  schema: "native_generate_request",
  defaults: "native_generate_defaults",
  data: {
    prompt: @task.input.text,
    model: "local-model",
    max_length: 256
  },
  checks: ["complete"]
})

on("generate.request", "response", {
  bind: "generate.response",
  schema: "native_generate_response",
  checks: ["complete"]
})
```

## Why this is better

Compared to a procedural field-by-field DSL, this shape is:

- more declarative
- more compact
- easier to validate
- easier to template
- easier to map into JSON-like structures

## Main forms

The first useful forms are:

- `emit(name, spec)`
- `on(source, event, spec)`

These two forms are enough to express the first safe generate flows.

## `emit(...)`

`emit(...)` declares a structured object/event to create or send.

Example:

```js
emit("generate.request", {
  schema: "native_generate_request",
  defaults: "native_generate_defaults",
  data: {
    prompt: @task.input.text,
    model: "local-model",
    max_length: 256
  },
  checks: ["complete"]
})
```

### Suggested fields

Useful initial fields:

- `schema`
- `defaults`
- `data`
- `checks`
- `meta`
- `target`

Not all are required at MVP stage.

## `on(...)`

`on(...)` declares what should happen when an event occurs on a named object or stream.

Example:

```js
on("generate.request", "response", {
  bind: "generate.response",
  schema: "native_generate_response",
  checks: ["complete"]
})
```

### Suggested fields

Useful initial fields:

- `bind`
- `schema`
- `checks`
- `emit`
- `project`
- `meta`

## No embedded code

The DSL should avoid embedded runtime code like:

```js
handler: async (event) => { ... }
```

That is too open-ended and turns the DSL into a general-purpose language.

Prefer declarative handler data instead.

Good:

```js
on("generate.request", "response", {
  bind: "generate.response",
  emit: ["response.output_message"]
})
```

## Relation to lower layers

This event DSL should compile downward into lower-level Atomic assembly steps.

For example:

```js
emit("generate.request", {...})
```

may compile into:

- declare request object
- apply defaults
- fill fields
- run completeness check
- emit request message

And:

```js
on("generate.request", "response", {...})
```

may compile into:

- subscribe to response
- bind response object
- run checks
- emit output message

## Example: Task input + generate

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

## Example: generate output message

```js
on("generate.request", "response", {
  bind: "generate.response",
  schema: "native_generate_response",
  checks: ["complete"],
  emit: ["response.output_message"]
})
```

This keeps response handling compact while still explicit.

## Example: response table projection

```js
on("generate.request", "response", {
  bind: "generate.response",
  schema: "native_generate_response",
  checks: ["complete"],
  emit: ["response.output_message"],
  project: ["response.table"]
})
```

This works well with the existing `json <-> table <-> data` direction.

## Relation to local scopes

This DSL can later use local refs naturally:

```js
emit("generate.request", {
  data: {
    prompt: @task.input.text
  }
})
```

and:

```js
on("response.output_message", "edit", {
  project: ["response.table"]
})
```

So it stays compatible with the local-scope event model.

## Suggested MVP contract

For the first version, it is enough if the DSL supports:

- `emit`
- `on`
- `schema`
- `defaults`
- `data`
- `checks`
- `bind`

Everything else may come later.

## Why this fits Atomic

This syntax works well because:

- it is message/event-friendly
- it is easy to serialize
- it is easy to display as JSON or tables
- it maps well to object graphs
- it is easier for models than a custom procedural command language

## Short summary

Atomic can use a declarative event DSL as its upper layer:

- `emit(...)`
- `on(...)`

This gives a readable, model-friendly surface while still compiling down into explicit lower-level Atomic steps.
