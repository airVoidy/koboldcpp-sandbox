# Atomic Message With Annotations Example v0.1

## Purpose

This document shows one concrete example of how a message and its annotations may live together.

The goal is to make the model explicit:

- one message
- one raw text container
- multiple annotation objects
- all in the same message

## Example message

```json
{
  "message_id": "msg_demoness_001",
  "containers": [
    {
      "kind": "text",
      "name": "main_text",
      "data": {
        "text": "Anime demoness with obsidian horns, glowing amber eyes, and a proud side-facing pose."
      }
    }
  ],
  "annotations": [
    {
      "kind": "annotation",
      "source": {
        "message_ref": "msg_demoness_001",
        "container_ref": "main_text",
        "char_start": 0,
        "char_end": 14,
        "char_len": 14
      },
      "tags": ["style", "anime"],
      "meta": {
        "label": "style_phrase"
      }
    },
    {
      "kind": "annotation",
      "source": {
        "message_ref": "msg_demoness_001",
        "container_ref": "main_text",
        "char_start": 20,
        "char_end": 34,
        "char_len": 14
      },
      "tags": ["demoness_hint", "horns"],
      "meta": {
        "label": "horn_phrase"
      }
    },
    {
      "kind": "annotation",
      "source": {
        "message_ref": "msg_demoness_001",
        "container_ref": "main_text",
        "char_start": 36,
        "char_end": 54,
        "char_len": 18
      },
      "tags": ["appearance_trait", "eyes"],
      "meta": {
        "label": "eye_phrase"
      }
    },
    {
      "kind": "annotation",
      "source": {
        "message_ref": "msg_demoness_001",
        "container_ref": "main_text",
        "char_start": 62,
        "char_end": 85,
        "char_len": 23
      },
      "tags": ["pose"],
      "meta": {
        "label": "pose_phrase"
      }
    },
    {
      "kind": "annotation",
      "source": {
        "message_ref": "msg_demoness_001",
        "container_ref": "main_text",
        "char_start": 36,
        "char_end": 85,
        "char_len": 49
      },
      "tags": ["comment_anchor"],
      "meta": {
        "thread_ref": "thread_pose_and_eyes_001",
        "author": "user",
        "note": "Проверить, не пересекается ли это с uniqueness по глазам и позе."
      }
    }
  ],
  "meta": {
    "kind": "generated_output",
    "source_request_ref": "generate.request",
    "source_call_ref": "generate.call"
  }
}
```

## What this example shows

The same message contains:

- one main text container
- four semantic annotations
- one comment-anchor annotation

All annotations point back into the same text container.

## Why this is useful

This keeps the message self-contained.

You can inspect:

- the raw text
- the semantic tags
- the comment anchor
- the source metadata

without looking anywhere else by default.

## Overlap example

In the example above:

- the `eyes` annotation covers one phrase
- the `pose` annotation covers another phrase
- the `comment_anchor` spans over both of them

This demonstrates why overlapping annotations are natural in this model.

## Table projection example

The same message could later be projected into a table like:

| label | tags | char_start | char_end | text |
|---|---|---|---|---|
| style_phrase | [style, anime] | 0 | 14 | Anime demoness |
| horn_phrase | [demoness_hint, horns] | 20 | 34 | obsidian horns |
| eye_phrase | [appearance_trait, eyes] | 36 | 55 | glowing amber eyes |
| pose_phrase | [pose] | 62 | 85 | proud side-facing pose |

This shows how `message -> annotations -> table` fits the Atomic direction.

## Short summary

The practical default is:

- keep raw text in a message container
- keep annotations in the same message
- use `source + tags + meta`

This gives a simple and strong base for text-bound Atomic metadata.
