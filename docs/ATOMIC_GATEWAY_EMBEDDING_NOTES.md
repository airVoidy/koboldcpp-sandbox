# Atomic Gateway Embedding Notes

## Core idea

Each time data crosses an Atomic gateway, that event is valuable enough to be recorded as a lightweight semantic artifact.

This does **not** mean every crossing must immediately produce a full embedding vector.
It means every crossing should produce enough structured information so that embedding, clustering, route mining, and replay remain possible later.

## Minimal event model

For every gateway crossing, record:

- local `gen_id`
- worker role / endpoint
- input refs
- output refs
- transform type
- checkpoint from
- checkpoint to
- timing / benchmark data

This already forms a weak semantic fingerprint.

## Why `gen_id` matters

`gen_id` is not only a runtime handle.
In combination with:

- input frame refs
- output frame refs
- transform metadata
- timing
- acceptance result

it becomes a compact identity for a model-mediated transform.

That identity is useful for:

- replay
- stability testing
- route comparison
- clustering similar operations
- future embedding/indexing

## Embedding policy

Atomic should allow three levels:

### Level 0

No eager embeddings.
Only store structured lineage and benchmark metadata.

### Level 1

Store cheap text fingerprints / hashes / summaries at gateway crossings.

### Level 2

When resources are free, background jobs may produce:

- embedding vectors
- cluster links
- similarity candidates
- route hints

## Suggested record shape

```json
{
  "gen_id": "gen_local_0042",
  "worker_role": "generator",
  "endpoint": "http://localhost:5001",
  "checkpoint_from": "raw_input",
  "checkpoint_to": "constraints",
  "transform_type": "generate_manifest",
  "input_refs": ["msg_0012", "blk_0007"],
  "output_refs": ["msg_0017", "tbl_constraints_01"],
  "latency_ms": 842,
  "accepted": true
}
```

Even without an embedding vector, this is already rich enough to index and compare.

## Design rule

Every gateway crossing should be treated as a place where we may:

- benchmark
- serialize lineage
- attach a semantic fingerprint
- optionally enqueue background embedding

## Summary

In Atomic, a gateway crossing is a semantically meaningful event.

The system should preserve that event in a structured way so that:

- local routing can improve over time
- similar transforms can be clustered
- embeddings can be added lazily instead of eagerly

