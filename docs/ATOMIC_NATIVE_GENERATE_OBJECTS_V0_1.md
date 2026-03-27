# Atomic Native Generate Objects v0.1

## Purpose

This document defines the first concrete objects for the safe `generate` DSL flow.

These objects match the current repo-native generate path.

They are intended to work with:

- `object`
- `apply_defaults`
- `fill`
- `check_complete`
- `call`
- `bind_response`

## Current native endpoint

Current request target:

- `/api/v1/generate`

Current request shape in the repo:

- `prompt`
- `temperature`
- `max_length`
- `model`

## Object: `native_generate_request`

This is the first request object shape.

### Fields

| field | type | required | default | notes |
|---|---|---|---|---|
| `prompt` | `str` | yes | `""` | main generation input |
| `temperature` | `float` | no | `0.2` | sampling control |
| `max_length` | `int \| null` | no | `null` | completion limit |
| `model` | `str \| null` | no | `null` | optional route/model override |

### Aliases

Useful aliases:

- `generate.prompt`
- `request.prompt`
- `generate.temperature`
- `request.temperature`
- `gen.temp`
- `generate.max_length`
- `request.max_length`
- `generate.model`
- `request.model`

### Example declaration

```text
object generate.request using native_generate_request
```

## Object: `native_generate_defaults`

This is the default preset used before explicit fill.

### Suggested value set

```json
{
  "prompt": "",
  "temperature": 0.2,
  "max_length": null,
  "model": null
}
```

### Example use

```text
apply_defaults generate.request from native_generate_defaults
```

## Object: `native_generate_response`

This is the first response object shape for the safe flow.

It should not pretend the endpoint already returned a high-level parsed artifact.

It should stay close to what actually happened.

### Fields

| field | type | required | default | notes |
|---|---|---|---|---|
| `raw_response` | `dict \| null` | yes | `null` | full endpoint response |
| `raw_text` | `str` | no | `""` | extracted text content |
| `status` | `str` | yes | `"pending"` | lifecycle state |
| `output_message_ref` | `str \| null` | no | `null` | emitted message target |

### Why this shape

This keeps the first response object honest:

- full raw response is preserved
- extracted raw text is explicit
- message output is linkable
- lifecycle state is visible

## Suggested response states

Useful starting states:

- `pending`
- `completed`
- `error`
- `timeout`

This set may later expand.

## Example safe flow

```text
object generate.request using native_generate_request
apply_defaults generate.request from native_generate_defaults

fill generate.request:
  prompt = @task.input.text
  model = "local-model"
  max_length = 256

check_complete generate.request
call generate with generate.request -> generate.call

object generate.response using native_generate_response
bind_response generate.call -> generate.response
check_complete generate.response
```

## Expected response binding

`bind_response` should populate:

- `raw_response` from the full endpoint payload
- `raw_text` from:
  - `results[0].text` for native mode
  - or extracted text equivalent if adapted elsewhere
- `status` from call outcome
- `output_message_ref` from the emitted response message, if created during binding

## Relation to message containers

The response object does not replace the message layer.

Instead:

- response object is the structured runtime object
- response message is the visible carrier artifact

Both may coexist and link to each other.

## Short summary

The first concrete generate objects should be:

- `native_generate_request`
- `native_generate_defaults`
- `native_generate_response`

They are small, explicit, and close to the actual repo contract, which makes them a safe base for the first Atomic `generate` flow.
