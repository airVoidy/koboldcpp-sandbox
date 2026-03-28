# ATOMIC Wiki Text Scope Bridge v0.1

## Purpose

Define `wiki` as the default explicit scope layer for text-like data in Atomic.

This replaces direct `global/local variable` usage as the primary model for durable text state.


## Core Rule

- text-like state should prefer `wiki-like message artifacts`
- direct mutable vars may still exist at runtime
- but canonical readable/writable text state should be exposed through `wiki`


## Why

- keeps state visible
- keeps state message-based
- avoids hidden global text buffers
- makes lineage/source refs easier to preserve
- fits `L1 = messages`
- works well with `json <-> table <-> data`


## Separation

- `wiki`
  - text-oriented durable or semi-durable scope
  - prompt fragments
  - task inputs
  - summaries
  - extracted notes
  - shared text artifacts

- `object/table/checkpoint`
  - operational structured state
  - request objects
  - parsed tables
  - resolved payloads
  - mid-layer transforms

- `runtime vars`
  - temporary execution glue
  - allowed, but not the preferred canonical surface for text state


## Practical Shift

Prefer this:

```text
wiki/task.input
wiki/generate.request.prompt
wiki/entity.eye_colors
wiki/summary.unique_traits
```

Instead of treating text primarily as:

```text
$input
$prompt
$notes
$summary
```


## Access Model

Text access should go through small explicit endpoints or equivalent bindings.

Examples:

- build wiki artifact from message annotations
- merge new extracted values into existing wiki artifact
- resolve wiki text into prompt/object input
- project wiki text into table/object checkpoints


## Relationship To DSL

- `emit/on` may refer to wiki artifacts by ref
- assembly may read/write wiki artifacts through explicit calls
- workflow/v2 may orchestrate wiki-producing and wiki-consuming steps

`wiki` is not a separate storage ontology.
It is a text-facing message pattern.


## Canonical Mental Model

- `wiki` replaces hidden text variables
- `message` remains the real carrier
- `wiki-like artifact` is a named readable text surface
- structured processing still happens through object/table/checkpoint layers


## Recommended Default

For text-heavy pipelines:

1. create or update a wiki-like message artifact
2. attach source refs / annotations
3. project to table/object if structured work is needed
4. write results back into wiki/message form


## Example

Task input:

- `wiki/task.input`

Generated answer:

- `wiki/task.answer.raw`

Extracted unique eye colors:

- `wiki/task.unique.eye_colors`

Structured generate request:

- `object/generate.request`

Response parsing table:

- `table/generate.response.annotations`


## Summary

Atomic should treat `wiki` as the default explicit scope for text data,
while `object/table/checkpoint` remain the structured operational layer.
