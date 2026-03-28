# ATOMIC Data Scope Namespace v0.1

## Purpose

Define `data/...` as the top-level scope namespace for Atomic artifacts.

`wiki/...` should not be the top namespace.
It should be treated as one default template/kind for text-oriented data artifacts.


## Core Rule

- top-level namespace: `data/...`
- `wiki` is a data kind/template
- other kinds may live in the same namespace:
  - `wiki`
  - `object`
  - `table`
  - `message`
  - `checkpoint`


## Canonical Shape

Prefer:

```text
data/local/wiki/task.input
data/local/object/generate.request
data/local/table/response.annotations
data/global/wiki/colors.eyes
data/global/table/trait.index
```

Instead of:

```text
wiki/local/task.input
wiki/global/colors.eyes
```


## Why

- keeps the namespace generic
- avoids overfitting the whole system to text-only artifacts
- fits the broader Atomic goal:
  local agent data/runtime framework
- makes `wiki` one reusable pattern among several
- works better with message/object/table/checkpoint layers


## Data Scope Layers

- `data/local/...`
  - task-local working state
  - tree-local artifacts
  - local summaries
  - temporary or checkpointed structured objects

- `data/global/...`
  - promoted shared artifacts
  - reusable summaries
  - consolidated indexes/lists
  - user-level durable artifacts


## Artifact Kinds

### `data/.../wiki/...`

Default text-oriented artifact template.

Use for:

- task inputs
- notes
- summaries
- extracted text facts
- prompt fragments


### `data/.../object/...`

Structured jsonlike object artifacts.

Use for:

- request objects
- response objects
- config bundles
- worker payloads


### `data/.../table/...`

Structured tabular artifacts.

Use for:

- annotation rows
- parameter legends
- parsed entity tables
- comparison matrices


### `data/.../message/...`

Raw or structured message-carrier artifacts.


### `data/.../checkpoint/...`

Checkpoint-oriented artifacts or bundles.


## Recommended Flow

For text-heavy tasks:

1. store input in `data/local/wiki/...`
2. derive structured forms in `data/local/object/...` or `data/local/table/...`
3. verify / enrich / merge
4. explicitly promote useful results into `data/global/...`


## Example

For demoness parsing:

```text
data/local/wiki/task.input
data/local/wiki/task.answer.raw
data/local/table/task.answer.annotations
data/local/wiki/entity.eye_colors
data/local/wiki/entity.hair_colors
data/global/wiki/colors.eyes
data/global/wiki/colors.hair
```


## Summary

Atomic should use `data/...` as the main scope namespace.
`wiki/...` remains important, but as a default text data template inside that namespace.
