# ATOMIC Wiki Container Ref Model v0.1

## Purpose

Define `wiki` refs as container-level refs, not field-level refs.

This avoids overcommitting too early to a rigid internal field path model.


## Core Rule

Prefer:

```text
@data.local.wiki.task.input
```

Not:

```text
@data.local.wiki.task.input.text
```

as the default canonical reference.


## Why

`wiki` is better treated as a text/data artifact container, not as one fixed field bag.

A single wiki artifact may contain:

- main text
- multiple text blocks
- annotations
- comments
- table nodes
- spans
- derived local inputs

So a direct `.text` suffix is too narrow as a general architectural default.


## Better Mental Model

`wiki` ref:

- points to the whole artifact/container
- does not assume one exact internal slot

Then a second step resolves the needed surface:

- default text surface
- named slot
- table projection
- annotation view


## Two-Step Access

### Step 1

Reference the artifact:

```text
@data.local.wiki.task.input
```

### Step 2

Choose the surface:

```text
read_text(@data.local.wiki.task.input)
resolve_slot(@data.local.wiki.task.input, "main_text")
project_table(@data.local.wiki.task.input)
annotations(@data.local.wiki.task.input)
```


## Consequence For DSL

Do not assume that:

```text
@data.local.wiki.task.input.text
```

is the universal stable form.

Safer direction:

- artifact ref first
- surface selection second


## Relation To Message-Based L1

This fits the message/container model better:

- `wiki` stays a container artifact
- message internals stay flexible
- text/annotations/tables can coexist inside one artifact
- projection to `N*M` matrix or table remains a separate mid-layer decision


## Recommended Default

For early Atomic examples:

- use `@data.local.wiki.task.input` as the main ref
- explicitly call a surface resolver when text is needed
- avoid hardcoding `.text` unless the template guarantees it


## Example

Instead of:

```text
prompt: @data.local.wiki.task.input.text
```

Prefer:

```text
prompt: read_text(@data.local.wiki.task.input)
```

Or:

```text
prompt_source: @data.local.wiki.task.input
prompt_surface: "main_text"
```


## Summary

`wiki` refs should default to container-level references.

Field-level access should be a second explicit step, not the primary architectural assumption.
