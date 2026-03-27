# Atomic Table Object Model v0.1

## Purpose

This document defines a simple universal mid-layer for Atomic data objects:

- raw JSON or raw message payload remains intact
- a structured object schema describes fields
- the working view is primarily table-oriented
- table cells may later gain macro wrappers and tag metadata

This is meant as a practical MVP for:

- serialization/deserialization
- table checkpoints
- alias-based access
- programmable field access
- later tree-of-tables expansion

## Core rule

For data-heavy Atomic tasks, the easiest operational mid-layer is:

1. raw payload
2. schema/object wrapper
3. table projection

The raw payload is not destroyed.
The table projection is the main working surface.

## Envelope

The preferred minimal envelope is:

```json
{
  "table_data": { ... },
  "meta_data": { ... }
}
```

Rules:

- `table_data` is the canonical working payload for the mid-layer
- `meta_data` is flexible and only needs to remain valid structured metadata
- no heavy global formal constraints are required for `meta_data` at MVP level

## Object model

The intended layers are:

1. `ObjectField`
2. `ObjectSchema`
3. `TableObject`
4. `TableProjection`

## ObjectField

An `ObjectField` should define:

- canonical field name
- type
- default
- aliases
- group
- description
- required flag

This gives both:

- schema meaning
- table legend meaning

## ObjectSchema

An `ObjectSchema` defines a structured object shape once.

From the schema, the system should get automatically:

- alias resolution
- JSON import
- JSON export
- table export
- field lookup

## TableObject

A `TableObject` is one concrete instance of a schema.

It should preserve:

- current values
- schema link
- alias access
- export to JSON
- export to table rows

## TableProjection

The working table should behave like a legend of programmable access.

That means each row should ideally expose:

- canonical field name
- type
- value
- default
- aliases
- group
- path
- required flag

Example row:

| field | group | type | value | default | aliases | path |
|---|---|---|---|---|---|---|
| temperature | sampler | float | 0.5 | 0.5 | `["gen.temp","sampler.temperature"]` | `generate.params.temperature` |

## Why this is useful

This gives one object several readable views:

- raw JSON view
- structured object view
- table view

And the table view is especially useful because:

- it is denser than tree-only display
- it is easier to patch incrementally
- it is easier to use as a checkpoint
- it is easier to drive from aliases and events

## Generate params example

A `generate.params` object may look like:

```json
{
  "max_context_length": 2048,
  "max_length": 100,
  "prompt": "Niko the kobold...",
  "quiet": false,
  "rep_pen": 1.1,
  "rep_pen_range": 256,
  "rep_pen_slope": 1,
  "temperature": 0.5,
  "tfs": 1,
  "top_a": 0,
  "top_k": 100,
  "top_p": 0.9,
  "typical": 1
}
```

And the working table may look like:

| field | type | value | default | aliases |
|---|---|---|---|---|
| max_context_length | int | 2048 | 2048 | [generate.max_context_length, ctx_len] |
| max_length | int | 100 | 100 | [generate.max_length] |
| prompt | str | "Niko the kobold..." | "" | [generate.prompt] |
| temperature | float | 0.5 | 0.5 | [gen.temp, sampler.temperature] |

## Aliases

Aliases are important because they allow:

- compact references
- semantic references
- grouped access
- user-facing references
- internal path compatibility

The system should resolve:

- canonical field names
- alias names
- path-like aliases

to the same canonical field.

## Path field

The table view should expose a programmable path for each row.

Example:

- `generate.params.temperature`
- `generate.prompt.text`

This is useful both for:

- DSL references
- event-based updates

## Table checkpoints

Tables should be first-class checkpoints.

That matters because many complex tasks become easier to formalize when the checkpoint is:

- one dense table
- with explicit rows
- with explicit aliases
- with explicit metadata

This is especially useful for:

- prompt decomposition
- param tuning
- constraint extraction
- block parsing
- probe outputs

## Cell macros

A later extension should allow macro wrappers inside cells.

This should work not only for value cells, but for any data cell.

Examples:

- reference macros
- derived-value macros
- tagged-value wrappers
- structured placeholders

Example direction:

```text
value = $ref(generate.defaults.temperature)
value = $tag(example_block)
value = $slice(msg_0012, 42, 81)
```

At MVP stage, this can stay as plain text in cells.

The important thing is that the table object model leaves room for it.

## Tags in cell data

Tags are useful here because one field or cell may later need:

- semantic labels
- source links
- variable-name hints
- example markers
- extraction markers

Example:

- generated example prompt text is later marked:
  - this slice is an example
  - this slice should become variable `character_name`

This fits naturally into table cell metadata and span metadata.

## Example prompt chunking use case

A generated example prompt may later be segmented into chunks.

Each chunk may be tagged with:

- variable name
- semantic role
- source span
- replacement policy

This suggests a later combination of:

- table object rows
- span metadata
- tagged cell macros

## Tree-of-tables compatibility

This model should work naturally inside a tree-of-tables view.

Examples:

- one node = `generate.params`
- one node = `generate.prompt`
- one node = `prompt.example_chunks`
- one node = `parsed.constraints`

Each node may be a table.

## Minimal MVP implementation

The first MVP only needs:

1. field schema
2. alias resolution
3. object instance
4. JSON import/export
5. table export

This is enough to test the hypothesis.

## Recommended row shape

A practical row shape is:

```json
{
  "field": "temperature",
  "group": "sampler",
  "type": "float",
  "value": 0.5,
  "default": 0.5,
  "aliases": ["gen.temp", "sampler.temperature"],
  "path": "generate.params.temperature",
  "required": false,
  "description": "Sampling temperature"
}
```

## Meta data usage

`meta_data` may hold:

- schema name
- schema hash
- shape hash
- source message refs
- checkpoint refs
- alias maps
- projection refs
- event hooks

At MVP stage, none of these should be mandatory except valid structure.

## Short summary

The Atomic table object model should be:

- simple
- explicit
- table-driven
- alias-friendly
- JSON-compatible
- ready for later cell macros and tags

It is meant to be a practical mid-layer between raw payloads and richer Atomic DSL flows.
