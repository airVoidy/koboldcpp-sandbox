# Source Ref Schema

## Purpose

Define one consistent source reference structure for all entities in the project.

This is needed for:

- provenance
- text extraction
- back-checking hypotheses
- comparing early and late reasoning layers
- rendering text with highlights
- validating that a derived claim still points to its textual basis

## Why It Matters

Without source references, the system only stores the current formalization.

With source references, the system can also store:

- where the claim came from
- which exact text tokens support it
- whether it is direct text or interpretation
- which earlier reasoning layer introduced it

This makes the framework safer and much easier to audit.

## Canonical Shape

Recommended canonical structure:

```json
{
  "source_ref": {
    "file": "",
    "version": "v0",
    "sentence_id": null,
    "fragment_id": null,
    "token_refs": [],
    "char_span": null,
    "surface_text": "",
    "source_kind": "question|condition|thought|worker|derived",
    "interpretation_level": "direct|light|strong"
  }
}
```

## Field Meaning

### `file`

Path or local logical file identifier where the source came from.

Examples:

- `source_text.md`
- `question.txt`
- `thoughts example.txt`

### `version`

Source snapshot version.

Examples:

- `v0`
- `v1`
- `pass-3`

Useful when later parsers or worker passes produce updated tokenizations.

### `sentence_id`

Identifier of the sentence in the source text.

May be null if not yet split.

Examples:

- `s-0001`
- `cond-04`

### `fragment_id`

Identifier of the smaller fragment inside a sentence.

Useful after splitting a sentence into relation-level parts.

Examples:

- `f-0001`
- `c1-frag-2`

### `token_refs`

List of token ids in the token index.

Examples:

- `["tok-0001", "tok-0002"]`

### `char_span`

Optional raw span in the original text.

Recommended shape:

```json
[start, end]
```

Can remain null until needed.

### `surface_text`

The exact local text slice for this object/claim/relation.

Useful for:

- rendering
- debugging
- human review

### `source_kind`

Indicates where the source came from.

Recommended values:

- `question`
- `condition`
- `thought`
- `worker`
- `derived`
- `historical`

### `interpretation_level`

How close the current object is to direct text.

Recommended values:

- `direct`
- `light`
- `strong`

Examples:

- `Диана не вошла первой` -> `direct`
- `author < 5` inferred from "fifth visitor found it already open" -> `light` or `strong`

## Where To Use It

The same schema should be used in:

- objects
- relations
- claims
- atoms
- derived facts
- shortcut hypotheses
- hole summaries

## Minimal Rule

If something exists in the system, it should have at least one `source_ref`.

Even for derived objects, `source_ref` should point to:

- the textual basis
- or the parent objects/claims that caused the derivation

## Recommended Extensions

Later we may add:

- `parent_refs`
- `worker_id`
- `tick_id`
- `layer_id`
- `confidence`

But these should be optional and not required for the first version.

## MVP Recommendation

For the current example, use at least:

```json
{
  "source_ref": {
    "file": "source_text.md",
    "version": "v0",
    "sentence_id": null,
    "fragment_id": null,
    "token_refs": [],
    "char_span": null,
    "surface_text": "",
    "source_kind": "question",
    "interpretation_level": "direct"
  }
}
```

Then later enrich with sentence and fragment ids as parsing improves.
