# Atomic Generate Safe DSL Draft v0.1

## Purpose

This document defines a safer minimal DSL shape for `generate`.

The goal is:

- avoid losing fields
- avoid implicit request assembly
- make missing fields visible before call time
- keep the syntax simple and explicit

## Core rule

Do not build a request as a loose sequence of field writes.

Instead, use a fixed safe flow:

1. declare object shape
2. apply defaults
3. fill explicit values
4. check completeness
5. call endpoint
6. bind response
7. check response completeness

## Why plain `set_field(...)` is risky

This style:

```text
set_field(generate.request.prompt, ...)
set_field(generate.request.temperature, ...)
set_field(generate.request.max_length, ...)
```

is too easy to break because:

- one field may be forgotten
- field names may drift
- order may hide missing setup
- request shape is not obvious at a glance

## Safer shape

The safer pattern is:

```text
object generate.request using native_generate_request
apply_defaults generate.request from native_generate_defaults

fill generate.request:
  prompt = @task.input.text
  max_length = 256

check_complete generate.request
call generate with generate.request -> generate.call

object generate.response using native_generate_response
bind_response generate.call -> generate.response
check_complete generate.response
```

## Required primitives

The minimal primitive set should be:

- `object`
- `apply_defaults`
- `fill`
- `check_complete`
- `call`
- `bind_response`

This is enough for a safe first layer.

## `object`

Declares a named object and its expected shape.

Example:

```text
object generate.request using native_generate_request
```

This should make the field set explicit before any values are written.

## `apply_defaults`

Copies default values from a known default object or schema preset.

Example:

```text
apply_defaults generate.request from native_generate_defaults
```

This reduces the number of manual assignments.

## `fill`

Writes only explicit overrides or task-derived values.

Example:

```text
fill generate.request:
  prompt = @task.input.text
  max_length = 256
```

This should only target declared fields.

If a field is unknown, it should fail visibly.

## `check_complete`

Checks the object before it is used.

It should verify at least:

- required fields are present
- no unknown fields were written
- field types are acceptable

Example:

```text
check_complete generate.request
```

This is the main anti-loss checkpoint.

## `call`

Runs the actual endpoint call using the checked request object.

Example:

```text
call generate with generate.request -> generate.call
```

This should create a call artifact, not just a raw return value.

## `bind_response`

Takes the call artifact and populates a response object.

Example:

```text
object generate.response using native_generate_response
bind_response generate.call -> generate.response
```

This keeps output shape explicit too.

## Minimal request shape example

For the current repo-native endpoint:

```text
object generate.request using native_generate_request
apply_defaults generate.request from native_generate_defaults

fill generate.request:
  prompt = @task.input.text
  model = "local-model"
  max_length = 256

check_complete generate.request
call generate with generate.request -> generate.call
```

## Minimal response shape example

```text
object generate.response using native_generate_response
bind_response generate.call -> generate.response
check_complete generate.response
```

The response object may include fields like:

- `raw_response`
- `raw_text`
- `status`
- `output_message_ref`

## Why this is safer

This shape reduces mistakes because:

- the object schema is declared first
- defaults are visible
- overrides are grouped
- completeness is checked before the call
- response shape is also declared explicitly

## Suggested failure behavior

`check_complete` should fail if:

- required field missing
- undeclared field written
- incompatible type detected

It should report all visible problems, not just the first one.

## Relation to message-based architecture

Each stage can still become its own message/action artifact:

- declared request object
- defaults applied
- filled request
- checked request
- call artifact
- bound response object

So this remains compatible with:

- message-based checkpoints
- replay
- revision history

## Short summary

For `generate`, the safe default DSL flow should be:

- `object`
- `apply_defaults`
- `fill`
- `check_complete`
- `call`
- `bind_response`
- `check_complete`

This is a better base than loose field-by-field mutation.
