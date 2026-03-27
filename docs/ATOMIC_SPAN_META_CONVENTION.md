# Atomic Span Meta Convention

## Purpose

This document defines the convention for text-linked Atomic metadata.

The goal is to support:

- raw message text as the stable source
- external annotation layers
- automatic serialization and deserialization
- matrix projection
- overlapping tags
- reliable writeback between message layer and mid-layer

## Core rule

If Atomic metadata annotates text, it should link back to the raw message text as directly as possible.

At minimum, span metadata should try to preserve:

- `message_ref`
- `char_start`
- `char_len`
- `char_end` or equivalent last-char boundary

When available, it should also preserve:

- `block_ref`
- token offsets
- line offsets
- projection refs

## Why this matters

This convention exists so the system can:

- reconstruct annotations from raw text
- project annotations into matrix form
- merge overlapping annotation layers
- serialize tagged arrays safely
- rehydrate mid-layer workspaces
- avoid destructive inline text rewriting

## Raw text rule

Raw message text should remain separate from annotation metadata.

That means:

- raw carrier text stays readable
- tags do not need to be embedded inline
- annotation layers can overlap freely
- different passes can annotate the same text differently

## Minimum span object

The minimum useful span object is:

```json
{
  "span_id": "span_00017",
  "message_ref": "msg_00017",
  "block_ref": "blk_0012",
  "char_start": 42,
  "char_len": 11,
  "char_end": 53,
  "text": "silver hair",
  "tag": "hair_color"
}
```

## Required fields

For text-bound metadata, the preferred minimum fields are:

- `span_id`
- `message_ref`
- `char_start`
- `char_len`
- `char_end`
- `tag`

If a block exists, also include:

- `block_ref`

## Recommended fields

Recommended extensions:

- `text`
- `value`
- `layer`
- `kind`
- `source_ref`
- `target_ref`
- `confidence`
- `token_start`
- `token_end`
- `token_len`
- `line_start`
- `line_end`
- `projection_ref`
- `checkpoint_ref`
- `revision_ref`

## Preferred boundary convention

Use explicit numeric boundaries.

Preferred fields:

- `char_start`
- `char_len`
- `char_end`

This is intentionally redundant.

If the values disagree, that should be treated as a consistency issue.

Recommended convention:

- `char_start` is inclusive
- `char_end` is exclusive
- `char_len = char_end - char_start`

If another convention is used in a specific subsystem, it must be declared explicitly.

## Optional last-char form

If useful for a subsystem, a last-char field may also be stored:

- `char_last`

But this should be treated as optional derived redundancy, not as the only boundary field.

## Block-relative and message-relative addressing

When possible, keep both:

- message-relative address
- block-relative address

Example:

```json
{
  "message_ref": "msg_00017",
  "block_ref": "blk_0012",
  "char_start": 42,
  "char_end": 53,
  "block_char_start": 5,
  "block_char_end": 16
}
```

This helps when:

- blocks are reprojected
- matrices operate on subregions
- the same message contains many independently tagged chunks

## Overlap policy

Overlapping spans are allowed.

This is important because one text segment may carry multiple annotations such as:

- semantic tag
- entity tag
- uniqueness tag
- probe warning
- contradiction marker
- source lineage mark

So overlap is not an error by default.

## Types of overlap

Useful overlap categories:

- exact overlap
- nested overlap
- partial overlap
- crossing overlap

This may later be useful for conflict detection and merge logic.

## Layering rule

Annotations should be distinguishable by layer.

Suggested field:

- `layer`

Examples:

- `entity_extract`
- `style_extract`
- `probe_uniqueness`
- `probe_contradiction`
- `ui_selection`
- `revision_diff`

This allows many span sets to coexist over the same raw text.

## Span identity rule

Do not rely only on positional coordinates as identity.

Use:

- stable `span_id`
- plus coordinates
- plus `message_ref`

This matters because:

- text may be reloaded
- projections may be rebuilt
- revisions may compare old and new span sets

## Relation to matrix projection

Span metadata is one of the main bridges into matrix projection.

Example matrix row:

| span_id | tag | message_ref | block_ref | char_start | char_end | char_len | text | layer |
|---|---|---|---|---|---|---|---|---|
| span_17 | hair_color | msg_17 | blk_12 | 42 | 53 | 11 | silver hair | entity_extract |

This means:

- raw storage remains message-based
- operations can still happen in matrix form

## Relation to sparse NxM mid-layer

When a page or task opens into sparse NxM workspace form:

- text spans may map to text regions
- metadata spans may map to meta regions
- AABB updates may target those regions

So span meta should be easy to project into:

- matrix coordinates
- region bounds
- update queues

Suggested optional fields:

- `matrix_ref`
- `row_ref`
- `col_ref`
- `aabb_ref`

## Serialization rule

Text plus span-meta arrays should serialize as:

1. raw text carrier
2. array of span objects
3. optional grouped views

Example:

```json
{
  "message_ref": "msg_00017",
  "text": "A demoness with silver hair and violet eyes...",
  "spans": [
    {
      "span_id": "span_1",
      "tag": "hair_color",
      "char_start": 16,
      "char_end": 27,
      "char_len": 11,
      "text": "silver hair"
    },
    {
      "span_id": "span_2",
      "tag": "eye_color",
      "char_start": 32,
      "char_end": 43,
      "char_len": 11,
      "text": "violet eyes"
    }
  ]
}
```

## Deserialization rule

Given raw text plus spans, the system should be able to:

- rebuild annotation arrays
- rebuild grouped tag views
- rebuild matrix rows
- rebuild overlap maps
- rebuild sparse workspace projections

This is why the positional metadata must stay explicit.

## Grouped serialization

For some tasks, grouped forms are useful in addition to flat span arrays.

Example grouped form:

```json
{
  "by_tag": {
    "hair_color": ["span_1"],
    "eye_color": ["span_2"]
  }
}
```

This grouped form is optional.
The flat span list remains the canonical annotation form.

## Update rule

If text changes in a way that invalidates spans, the system should not silently trust old coordinates.

Possible outcomes:

- span preserved
- span shifted
- span invalidated
- span requires reparse

This is especially important for repair loops and revision diffs.

## Confidence and provenance

For extracted or inferred annotations, keep provenance when possible.

Useful fields:

- `confidence`
- `producer`
- `source_ref`
- `checkpoint_ref`
- `gateway_event_ref`
- `probe_ref`

This helps distinguish:

- direct extracted facts
- inferred tags
- probe warnings
- UI-only marks

## Suggested typed span kinds

Suggested `kind` values:

- `entity_value`
- `style_value`
- `constraint_tag`
- `probe_warning`
- `probe_error`
- `lineage_mark`
- `ui_mark`
- `file_region`
- `link_region`

## File and link payloads

This convention can also extend beyond plain text snippets.

If a whole file or linked artifact is represented inside a message container, span-like metadata may still refer to:

- file-local offsets
- extracted text windows
- rendered text slices

In that case, keep both:

- carrier/message refs
- underlying file or link refs

## Minimal invariant set

The span-meta system should preserve:

1. raw text remains readable and primary
2. text annotations are externalized
3. spans link back to message-level carriers
4. redundant boundaries are preserved
5. overlaps are allowed
6. matrix projection stays reconstructible
7. serialization/deserialization remains automatic

## Short summary

Atomic span metadata should be treated as:

- external structured annotations over raw message text
- positionally explicit
- overlap-friendly
- easy to serialize
- easy to project into matrix mid-layer
- easy to write back into message-linked runtime artifacts
