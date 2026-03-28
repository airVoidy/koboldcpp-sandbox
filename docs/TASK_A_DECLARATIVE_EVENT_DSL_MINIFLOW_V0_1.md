# Task A Declarative Event DSL Miniflow v0.1

## Purpose

This document rewrites the minimal Task A `generate` flow using the upper declarative event DSL.

The goal is:

- keep the flow semantic
- keep the request shape explicit
- keep the response binding explicit
- avoid procedural field-by-field noise

## Task A text

```text
написать 4 описания внешности демониц в разных образах
[проверить, что разные образы, разный цвет глаз,
разный цвет волос, разные позы,
в описании должны быть элементы, по которым даже без указания расы понятно, что перед тобой демоница,
стиль: аниме, должен быть явно указан в описании]
```

## Miniflow

```js
emit("task.input", {
  target: "data.local.wiki.task.input",
  data: {
    text: "написать 4 описания внешности демониц в разных образах\n[проверить, что разные образы, разный цвет глаз,\nразный цвет волос, разные позы,\nв описании должны быть элементы, по которым даже без указания расы понятно, что перед тобой демоница,\nстиль: аниме, должен быть явно указан в описании]"
  }
})

emit("generate.request", {
  target: "data.local.object.generate.request",
  schema: "native_generate_request",
  defaults: "native_generate_defaults",
  data: {
    prompt: @data.local.wiki.task.input.text,
    model: "local-model",
    max_length: 512
  },
  checks: ["complete"]
})

on("generate.request", "response", {
  bind: "data.local.object.generate.response",
  schema: "native_generate_response",
  checks: ["complete"],
  emit: ["data.local.message.response.output_message"],
  project: ["data.local.table.response.table"]
})
```

## Notes

This is intentionally only the first `generate` batch.

It does not yet describe:

- split into 4 blocks
- parse
- verify
- repair

Those should come later as separate event-driven batches.
