# ATOMIC Revision Persistence Policy v0.1

## Purpose

Define revision persistence as a post-processing / maintenance concern,
not as the default side-effect of every DSL execution step.


## Core Rule

Do not treat revision commits as an automatic consequence of every `emit/on` or assembly action.

Prefer:

- execute pipeline logic first
- verify integrity
- decide what should persist
- then commit/promote selected artifacts


## Why

If persistence is wired directly into every low-level step:

- runtime becomes storage-shaped too early
- transient work pollutes durable history
- `temp/local/global` lifecycle becomes weaker
- maintenance concerns leak into the execution layer


## Better Direction

Use revision persistence from:

- maintenance workers
- garbage collect / cleanup passes
- integrity verification passes
- explicit checkpoint/publish/promote steps

Not from every normal execution instruction.


## Practical Interpretation

### Execution layer

Responsible for:

- producing artifacts
- transforming data
- generating responses
- building tables
- attaching annotations

### Maintenance / persistence layer

Responsible for:

- deciding what is worth keeping
- validating retained artifacts
- pruning temp artifacts
- computing object hashes
- writing revision manifests
- creating git-backed commits


## Scope Interaction

- `@data.temp`
  - often should not be committed
  - may still be inspected during debug

- `@data.local`
  - may be committed at checkpoints
  - good target for task-level retention

- `@data.global`
  - usually committed intentionally
  - should be more curated


## Object Policy

Objects do not need to be stored in full inside the revision layer.

A valid policy is:

- keep text-like artifacts explicitly
- keep object hashes in revision manifests
- optionally store full objects elsewhere only when needed


## Recommended Flow

1. run pipeline
2. produce local/temp artifacts
3. run integrity verification
4. run garbage collect / cleanup policy
5. select retained text/data refs
6. compute object hashes
7. write revision commit


## Consequence For Atomic DSL

`emit/on` and assembly should remain focused on execution semantics.

Revision persistence should be:

- explicit
- higher-level
- policy-driven

not silently embedded into every low-level action.


## Summary

Atomic should treat revision persistence as a post-pass concern handled by maintenance logic,
not as the default side-effect of the main DSL execution path.
