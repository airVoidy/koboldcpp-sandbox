# Atomic Checkpoint Carrier Spec v0.1

## Purpose

This document defines the checkpoint carrier model for Atomic.

The goal is:

- raw data never disappears
- every meaningful step stays replayable
- every marked fragment stays addressable
- comments, threads, tables, chunks, and patches can attach to the same base carrier

## Core idea

Each node-level checkpoint should own a document-like sparse carrier.

That carrier is the base surface for:

- raw text
- raw JSON text
- file payload text
- imported content
- derived fragments

Everything else should attach to it through explicit metadata and refs.

## Main rule

Checkpoint data should be:

- additive
- addressable
- message-based
- span-linked

Meaning:

- raw carrier stays preserved
- updates do not destroy origin data
- new layers are added as messages, containers, spans, patches, and projections

## Checkpoint structure

The practical shape is:

```text
[checkpoint message]
  [carrier container]
  [action messages...]
  [projection containers...]
  [thread/comment messages...]
```

## Carrier container

The carrier container is the base raw surface.

It may hold:

- raw text
- raw JSON serialized as text
- file text
- file reference
- URL-loaded content

Example:

```json
{
  "kind": "checkpoint_carrier",
  "data": {
    "carrier_type": "text",
    "content": "....raw data...."
  },
  "meta": {
    "source_message_ref": "msg_001",
    "source_kind": "generate_output"
  }
}
```

## Sparse carrier idea

The carrier should behave like a sparse document canvas.

That means:

- some regions may be unfilled
- some regions may only be referenced
- the end may be empty
- multiple overlays may point into the same content

This is not the source of truth storage format.

It is the checkpoint working substrate.

## Required addressing for text-bound metadata

Any text-bound mark should prefer to store:

- `message_ref`
- `container_ref`
- `char_start`
- `char_len`
- `char_end`

Optional:

- `block_ref`
- `token_start`
- `token_len`
- `token_end`

## Span object

A minimal span object may look like:

```json
{
  "message_ref": "msg_checkpoint_001",
  "container_ref": "carrier.main",
  "char_start": 42,
  "char_len": 16,
  "char_end": 58,
  "tags": ["example_chunk"]
}
```

## What can attach to spans

Anything meaningful may attach to a span:

- tag metadata
- variable naming hints
- prompt chunk markers
- parse markers
- verification notes
- contradiction markers
- implication markers
- user comments
- worker follow-up tasks

## Comment/thread model

A marked fragment should be able to start its own thread.

That means:

- one span
- may have one or more comment threads
- each thread is still message-based

Example:

```text
[checkpoint message]
  [carrier]
  [span: 42..58]
  [thread message: comment_thread_root]
  [thread message: reply_1]
  [thread message: reply_2]
```

This is intentionally close to document comments in tools like Dropbox Paper or Google Docs.

## Action messages

Each meaningful transform should be its own internal message.

Examples:

- `build_table`
- `extract_spans`
- `split_chunks`
- `patch_value`
- `resolve_json`
- `call_generate`
- `extract_raw_text`

One action = one internal message.

## Container update rule

Every container update should emit a new message.

Not:

- hidden in-place mutation

But:

- additive message event
- linked to prior state
- replayable later

## Projection containers

Derived representations should live in separate containers.

Examples:

- `response_table`
- `response_chunks`
- `response_spans`
- `resolved_json`
- `matrix_projection`

These should not replace the carrier.

They should link back to it.

## Why this is useful

This model gives:

- stable raw origin
- easy replay
- explicit derivations
- safe annotation layering
- threadable fragments
- no fear of data loss during transforms

## Example flow

```text
[checkpoint message]
  [carrier: raw generate text]
  [action: extract_raw_text]
  [action: build_response_table]
  [container: response_table]
  [action: split_response_chunks]
  [container: response_chunks]
  [action: add_span_tags]
  [container: response_spans]
```

## Additive update principle

Checkpoint carriers should prefer:

- append
- annotate
- project
- link

over:

- overwrite
- hide
- replace origin

## Short summary

Each Atomic checkpoint should have a document-like sparse carrier.

Raw data lives there.

Everything else:

- spans
- tables
- chunks
- comments
- patches
- worker actions

attaches to that carrier through explicit refs and additive message-based updates.
