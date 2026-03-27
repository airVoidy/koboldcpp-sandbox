# Atomic Message Annotations v0.1

## Purpose

This document defines the default way to store text annotations in Atomic.

The goal is:

- keep raw text and markup together
- avoid unnecessary external storage
- support overlapping annotations
- make span-linked tags and comments explicit

## Core rule

Text annotations should live in the same message as the source text.

They should behave like:

- comment-like objects
- tag-like objects
- span-linked metadata objects

So the default model is:

- raw text in a message container
- annotations in the same message
- each annotation points to a span in that text

## Minimal annotation object

The minimal shape is:

```json
{
  "kind": "annotation",
  "source": {
    "message_ref": "msg_001",
    "char_start": 39,
    "char_end": 57,
    "char_len": 18
  },
  "tags": ["eyes", "appearance_trait"],
  "meta": {}
}
```

## Required source fields

For text-bound annotations, store at least:

- `message_ref`
- `char_start`
- `char_end`
- `char_len`

Optional:

- `block_ref`
- `token_start`
- `token_end`
- `token_len`

## Why this is the default

This keeps the model simple:

- the message stays self-contained
- the source text is easy to inspect
- annotations stay close to what they describe
- links are explicit

It also avoids early overengineering with separate span stores.

## Annotation behavior

An annotation may represent:

- semantic tag
- parse mark
- variable hint
- example chunk
- comment anchor
- verification note
- contradiction marker
- implication marker

The base type can stay the same.

Meaning comes from:

- `tags`
- `meta`

## Example: semantic tag

```json
{
  "kind": "annotation",
  "source": {
    "message_ref": "msg_001",
    "char_start": 39,
    "char_end": 57,
    "char_len": 18
  },
  "tags": ["eyes", "appearance_trait", "demoness_hint"],
  "meta": {
    "label": "eye_phrase"
  }
}
```

## Example: comment anchor

```json
{
  "kind": "annotation",
  "source": {
    "message_ref": "msg_001",
    "char_start": 12,
    "char_end": 34,
    "char_len": 22
  },
  "tags": ["comment_anchor"],
  "meta": {
    "thread_ref": "thread_004",
    "author": "user"
  }
}
```

## Example: prompt chunk hint

```json
{
  "kind": "annotation",
  "source": {
    "message_ref": "msg_prompt_002",
    "char_start": 70,
    "char_end": 109,
    "char_len": 39
  },
  "tags": ["example_chunk", "prompt_fragment"],
  "meta": {
    "variable_name": "character_eyes"
  }
}
```

## Overlapping annotations

Overlapping annotations are allowed.

This is one reason not to force inline markup into raw text.

Instead:

- raw text stays unchanged
- multiple annotations may point to overlapping spans

## Message-local storage

The default storage model is:

- annotations live in the same message
- not in a separate file by default

If a message later grows very dense, a sidecar index may still be added.

But the default should stay message-local.

## Relation to tags

Annotations can be thought of as:

- tags with metadata

So instead of plain tags only, Atomic should prefer:

- `annotation` objects with:
  - `tags`
  - `source`
  - `meta`

This keeps tags expressive without losing structure.

## Relation to comments

Annotations can also behave like comment anchors.

That means one annotation may:

- point to a span
- start a thread
- collect replies

This fits the checkpoint-carrier model well.

## Short summary

Atomic should store text markup by default as `annotation` objects inside the same message.

Each annotation is:

- span-linked
- taggable
- metadata-friendly
- comment-compatible

This is the simplest strong default for text annotations.
