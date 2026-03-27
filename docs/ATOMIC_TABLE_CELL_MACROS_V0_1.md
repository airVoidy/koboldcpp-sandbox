# Atomic Table Cell Macros v0.1

## Purpose

This document defines a minimal extension path for table-driven Atomic objects:

- tables stay the main dense mid-layer view
- any cell may still hold structured data
- macros inside cells stay explicit and serializable
- tags and spans may be attached without destroying raw values

The goal is to let table checkpoints remain simple while still supporting:

- prompt chunk markup
- variable extraction hints
- references to message spans
- derived or deferred values

## Core rule

At MVP level, a table cell must support two modes:

1. plain value
2. wrapped value

Wrapped value is still data, not magic.

## Recommended cell envelope

The preferred minimal cell form is:

```json
{
  "value": "...",
  "meta": {}
}
```

For plain cells, the raw scalar may still be used directly.

For macro-aware cells, the wrapped form should be preferred.

## Macro-aware cell example

```json
{
  "value": "$slice(msg_prompt_001, 42, 81)",
  "meta": {
    "cell_kind": "macro",
    "macro_kind": "slice_ref",
    "message_ref": "msg_prompt_001",
    "char_start": 42,
    "char_end": 81,
    "tags": ["example_chunk", "prompt_fragment"]
  }
}
```

## Tagged plain-value example

```json
{
  "value": "red glowing eyes",
  "meta": {
    "cell_kind": "text",
    "tags": ["appearance_trait", "eyes", "demoness_hint"]
  }
}
```

## Cell kinds

Useful starting kinds:

- `plain`
- `text`
- `macro`
- `span_ref`
- `object_ref`
- `list`
- `table_ref`

This list should stay open-ended.

## Macro kinds

Useful starting macro kinds:

- `ref`
- `slice_ref`
- `var`
- `template_slot`
- `derived`
- `join`

Examples:

```text
$ref(generate.defaults.temperature)
$slice(msg_0012, 42, 81)
$var(character_name)
$join(example_chunks)
```

At MVP stage, these may remain plain strings plus metadata.

## Relation to span metadata

When a cell refers to text inside a message, the cell metadata should reuse the same address convention:

- `message_ref`
- `block_ref` when available
- `char_start`
- `char_len`
- `char_end`

This keeps table cells compatible with:

- span arrays
- matrix projections
- replayable reconstruction

## Prompt chunking use case

A generated prompt may later be split into chunks.

Each chunk may be stored in a row like:

| field | value | meta |
|---|---|---|
| example_01 | "silver hair, curled horns..." | `{tags:[example_chunk], variable_name:example_01}` |
| example_02 | `$slice(msg_prompt_001, 82, 140)` | `{cell_kind:macro, macro_kind:slice_ref}` |

This lets the system:

- keep the raw prompt intact
- mark reusable prompt fragments
- assign future variable names
- replay the chunking step

## Why this matters

Without a cell macro convention, table checkpoints quickly become hard to evolve.

With a lightweight wrapped-cell rule, the same table can hold:

- resolved values
- deferred references
- source spans
- semantic tags
- extraction hints

without introducing a second hidden representation.

## Minimal MVP

The MVP should only require:

1. scalar cells
2. wrapped cells with `value`
3. optional `meta`
4. string macro payloads
5. tags and span refs in metadata

No evaluator is required yet.

## Short summary

Atomic tables should stay simple, but any cell may later become:

- tagged
- linked
- macro-wrapped
- span-addressed

This keeps tables usable as dense checkpoints while leaving room for prompt markup and replayable transformations.
