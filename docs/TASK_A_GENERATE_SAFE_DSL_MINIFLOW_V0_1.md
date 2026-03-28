# Task A Generate Safe DSL Miniflow v0.1

## Purpose

This document shows one minimal end-to-end `generate` flow for Task A using the safe Atomic DSL pattern.

The goal is not full pipeline coverage yet.

The goal is just:

1. take task input
2. build a checked generate request
3. call generate
4. bind the response
5. keep every stage explicit

## Task A input

Task text:

```text
написать 4 описания внешности демониц в разных образах
[проверить, что разные образы, разный цвет глаз,
разный цвет волос, разные позы,
в описании должны быть элементы, по которым даже без указания расы понятно, что перед тобой демоница,
стиль: аниме, должен быть явно указан в описании]
```

## Minimal object set

This miniflow uses:

- `data.local.wiki.task.input`
- `data.local.object.generate.request`
- `data.local.object.generate.call`
- `data.local.object.generate.response`

## Minimal functional flow

```text
object data.local.wiki.task.input

fill data.local.wiki.task.input:
  text = "написать 4 описания внешности демониц в разных образах
[проверить, что разные образы, разный цвет глаз,
разный цвет волос, разные позы,
в описании должны быть элементы, по которым даже без указания расы понятно, что перед тобой демоница,
стиль: аниме, должен быть явно указан в описании]"

object data.local.object.generate.request using native_generate_request
apply_defaults data.local.object.generate.request from native_generate_defaults

fill data.local.object.generate.request:
  prompt = @data.local.wiki.task.input.text
  model = "local-model"
  max_length = 512

check_complete data.local.object.generate.request
call generate with data.local.object.generate.request -> data.local.object.generate.call

object data.local.object.generate.response using native_generate_response
bind_response data.local.object.generate.call -> data.local.object.generate.response
check_complete data.local.object.generate.response
```

## What this explicitly guarantees

This flow makes visible:

- where prompt text came from
- which request object was used
- which defaults were applied
- which fields were overridden
- that request completeness was checked before call
- that response binding also has a declared shape

## Expanded view by stage

### 1. Input object

```text
object data.local.wiki.task.input

fill data.local.wiki.task.input:
  text = "...Task A text..."
```

This keeps the task itself explicit as a local object.

### 2. Request object

```text
object data.local.object.generate.request using native_generate_request
apply_defaults data.local.object.generate.request from native_generate_defaults

fill data.local.object.generate.request:
  prompt = @data.local.wiki.task.input.text
  model = "local-model"
  max_length = 512
```

This avoids loose field mutation and keeps the request shape visible.

### 3. Request check

```text
check_complete data.local.object.generate.request
```

This should fail if:

- required fields missing
- unknown fields used
- invalid field types detected

### 4. Endpoint call

```text
call generate with data.local.object.generate.request -> data.local.object.generate.call
```

`data.local.object.generate.call` should be treated as a call artifact, not just a temporary return value.

### 5. Response object

```text
object data.local.object.generate.response using native_generate_response
bind_response data.local.object.generate.call -> data.local.object.generate.response
check_complete data.local.object.generate.response
```

This keeps output explicit too.

## Expected bound response shape

At this stage, the response object should stay close to reality:

- `raw_response`
- `raw_text`
- `status`
- `output_message_ref`

No fake high-level parse is assumed yet.

## Message-based interpretation

This same miniflow can be interpreted as a sequence of explicit message artifacts:

1. input message
2. request object message
3. checked request message
4. generate call message
5. response object message
6. output message with raw text container

That keeps it compatible with the message-based architecture.

## Immediate next step after this miniflow

The natural next batch after `data.local.object.generate.response` is:

- extract `raw_text`
- emit response message/container
- optionally build `response_table`

But that is intentionally outside this minimal draft.

## Short summary

The smallest useful Task A `generate` flow is:

- declare input
- declare request
- apply defaults
- fill request
- check request
- call endpoint
- bind response
- check response

This is the first clean explicit `generate` batch for Atomic.
