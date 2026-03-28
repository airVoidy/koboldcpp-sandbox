# Task A Generate Output Miniflow v0.1

## Purpose

This document defines the immediate next step after the minimal `generate` call flow.

The goal is:

1. take `generate.response`
2. extract `raw_text`
3. emit a visible output message
4. build the first usable response table checkpoint

This keeps `generate` from ending in a hidden runtime object.

## Input

This miniflow starts from:

- `data.local.object.generate.response`

which already exists after:

- request fill
- request check
- endpoint call
- response binding

## Minimal object set

This miniflow uses:

- `data.local.object.generate.response`
- `data.local.message.response.output_message`
- `data.local.table.response.table`

## Minimal functional flow

```text
check_complete data.local.object.generate.response

object data.local.message.response.output_message

fill data.local.message.response.output_message:
  text = @data.local.object.generate.response.raw_text
  kind = "generated_raw_text"
  source_call_ref = @data.local.object.generate.call
  source_request_ref = @data.local.object.generate.request

check_complete data.local.message.response.output_message
emit_message data.local.message.response.output_message

object data.local.table.response.table
build_table data.local.message.response.output_message.text -> data.local.table.response.table
check_complete data.local.table.response.table
```

## Why this step matters

Without this step, `generate` ends in a runtime response object only.

With this step, the result becomes:

- visible
- message-based
- table-projectable
- ready for next batches

## Stage breakdown

### 1. Re-check response

```text
check_complete data.local.object.generate.response
```

This ensures the bound response is still valid before further use.

### 2. Build output message object

```text
object data.local.message.response.output_message

fill data.local.message.response.output_message:
  text = @data.local.object.generate.response.raw_text
  kind = "generated_raw_text"
  source_call_ref = @data.local.object.generate.call
  source_request_ref = @data.local.object.generate.request
```

This turns the extracted text into a visible message-level object.

### 3. Emit message

```text
check_complete data.local.message.response.output_message
emit_message data.local.message.response.output_message
```

At this point, the generated text exists as a real visible carrier.

### 4. Build first response table

```text
object data.local.table.response.table
build_table data.local.message.response.output_message.text -> data.local.table.response.table
check_complete data.local.table.response.table
```

This creates the first operational checkpoint over the generated text.

## What `data.local.table.response.table` should contain

At minimum:

- one or more rows representing the generated text
- refs back to the output message
- row metadata for later chunks/spans/tags

It does not need to be highly structured yet.

The first version may simply be:

- one row with the whole raw text
- one path
- one source ref

## Practical interpretation

This means `generate` should not stop at:

- raw response
- raw text

It should continue until the system has:

- visible output message
- first table checkpoint

That is the first actually usable downstream state.

## Next step after this miniflow

The natural next batch is:

- split response into chunks or blocks
- build spans
- attach tags
- optionally build parse table

For Task A that likely means:

- split into four demoness blocks

## Short summary

The minimal post-generate output flow should be:

- check response
- build output message
- emit output message
- build response table
- check response table

This gives the first useful checkpoint after the endpoint call.
