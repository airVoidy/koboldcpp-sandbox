# Atomic Data DSL v0.1

## Purpose

This document defines a separate DSL for the Atomic data layer.

It is not the same thing as:

- semantic task DSL
- worker/generate DSL
- prompt factory DSL

Its job is narrower:

- represent raw data explicitly
- serialize and deserialize it
- project it into table/tree forms
- patch it without hidden logic
- stay close to AST and message containers

## Core rule

The Data DSL is for data handling, not for agent intent.

It should answer:

- what data object exists
- what raw payload it carries
- what structured view is built over it
- what transform happened between formats

## Design goals

- explicit
- verbose if needed
- model-friendly
- replayable
- AST-like
- table-compatible
- message-compatible

## Main idea

The basic unit is a data object.

A data object may contain:

- raw text
- raw JSON
- table projection
- tree projection
- metadata
- refs to messages, files, URLs, spans

The Data DSL should mostly describe:

1. object declarations
2. projections
3. transforms
4. patches
5. serialization checkpoints

## Layer boundary

The stack should look like:

1. `Message Layer`
2. `Data DSL`
3. `Assembly DSL`
4. `Semantic DSL`

Meaning:

- message layer stores canonical visible data
- data DSL describes structured data work over it
- assembly DSL wires runtime operations
- semantic DSL provides higher abstractions

## Object form

The canonical object envelope stays:

```json
{
  "table_data": { ... },
  "meta_data": { ... }
}
```

But the Data DSL must also support raw-first objects.

Example:

```json
{
  "raw_data": {
    "kind": "text",
    "value": "Write 4 demoness descriptions..."
  },
  "meta_data": {
    "message_ref": "msg_task_a_001"
  }
}
```

## AST-like principle

The Data DSL should look closer to a data AST than to a programming language.

That means:

- declarations over commands
- nodes over statements
- transforms over hidden runtime effects

## Minimal node kinds

Useful starting node kinds:

- `object`
- `raw_text`
- `raw_json`
- `table`
- `tree`
- `field`
- `row`
- `cell`
- `span_ref`
- `file_ref`
- `url_ref`
- `transform`
- `patch`
- `serialize`
- `deserialize`

## Recommended top-level shape

The DSL should be representable as a simple tree:

```text
[object generate.request]
  [raw_json]
  [table]
  [meta]
```

or in explicit AST form:

```json
{
  "node": "object",
  "name": "generate.request",
  "children": [
    {"node": "raw_json", "value": {...}},
    {"node": "table", "value": {...}},
    {"node": "meta", "value": {...}}
  ]
}
```

## Recommended primitive operations

The Data DSL should keep operations extremely small.

Good primitives:

- `declare_object`
- `attach_raw_text`
- `attach_raw_json`
- `build_table`
- `build_tree`
- `patch_field`
- `patch_row`
- `patch_cell`
- `attach_meta`
- `serialize_json`
- `deserialize_json`
- `serialize_table`
- `deserialize_table`

These should be simple enough to resolve deterministically.

## Example: native generate request

Input JSON:

```json
{
  "prompt": "Write 4 demoness descriptions.",
  "temperature": 0.35,
  "max_length": 256,
  "model": "local-model"
}
```

AST-like Data DSL view:

```json
{
  "node": "object",
  "name": "generate.request",
  "children": [
    {
      "node": "raw_json",
      "value": {
        "prompt": "Write 4 demoness descriptions.",
        "temperature": 0.35,
        "max_length": 256,
        "model": "local-model"
      }
    },
    {
      "node": "table",
      "value": {
        "rows": [
          {
            "field": "prompt",
            "type": "str",
            "value": "Write 4 demoness descriptions.",
            "path": "generate.request.prompt"
          },
          {
            "field": "temperature",
            "type": "float",
            "value": 0.35,
            "path": "generate.request.temperature"
          }
        ]
      }
    },
    {
      "node": "meta",
      "value": {
        "schema_name": "native_generate_request",
        "endpoint": "/api/v1/generate"
      }
    }
  ]
}
```

## Raw text first

Raw text should be treated as a first-class data payload, not as a special case.

Example:

```json
{
  "node": "object",
  "name": "task.input",
  "children": [
    {
      "node": "raw_text",
      "value": "написать 4 описания внешности демониц..."
    },
    {
      "node": "meta",
      "value": {
        "message_ref": "msg_task_a_001",
        "kind": "task_input"
      }
    }
  ]
}
```

## Table projection

Table projection is the preferred working surface.

Rules:

- raw payload remains intact
- table projection may be rebuilt
- table rows should expose programmable paths
- tables are valid checkpoints

## Tree projection

Tree projection is for structure, not density.

The preferred visual substrate is:

- tree of tables

Meaning:

- object tree for navigation
- table nodes for dense data work

## Patches

Patches should also be data-like.

Example:

```json
{
  "node": "patch",
  "target": "generate.request.temperature",
  "value": 0.5,
  "meta": {
    "reason": "sampling_update"
  }
}
```

This is better than implicit mutation because it is replayable.

## Serialization checkpoints

Useful checkpoint kinds:

- `raw_text_checkpoint`
- `raw_json_checkpoint`
- `table_checkpoint`
- `tree_checkpoint`
- `resolved_json_checkpoint`

The Data DSL should be able to move between these forms without losing refs and metadata.

## Relation to macros

Cell macros belong naturally to the data layer.

But the DSL should treat them as explicit wrapped values, not hidden syntax magic.

Example:

```json
{
  "node": "cell",
  "value": "$slice(msg_0012, 42, 81)",
  "meta": {
    "cell_kind": "macro",
    "macro_kind": "slice_ref"
  }
}
```

## Relation to span metadata

When data is text-bound, the DSL should support span refs with:

- `message_ref`
- `block_ref`
- `char_start`
- `char_len`
- `char_end`

This keeps serialization/deserialization deterministic.

## Why separate Data DSL is useful

Without a dedicated data layer, too much logic leaks into:

- prompt factories
- worker wrappers
- semantic task flows

With a separate Data DSL:

- raw payload handling becomes explicit
- checkpoint shapes become predictable
- table transforms become reusable
- higher layers stay cleaner

## Minimal MVP

The first MVP only needs:

1. object declarations
2. raw text attachment
3. raw JSON attachment
4. table projection
5. cell metadata
6. patch nodes
7. serialize/deserialize nodes

That is enough to support:

- generate request inspection
- prompt chunk markup
- constraint tables
- parsed block tables

## Short summary

Atomic should have a separate Data DSL that is:

- AST-like
- raw-data-first
- table-driven
- replayable
- message-compatible

This gives a clean base under worker calls and higher-level Atomic functions.
