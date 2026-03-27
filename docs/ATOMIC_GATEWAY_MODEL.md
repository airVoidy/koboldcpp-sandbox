# Atomic Gateway Model

## Core idea

In the Atomic system, a `worker` should be treated primarily as a gateway/endpoint, not as a rich user-facing object.

This means:

- a worker is an execution surface
- a worker is usually a queue boundary
- a worker is often single-capacity or low-capacity
- a worker is where format conversion between local runtime data and model-facing payload happens

## Why this model is better

For Atomic tasks, the most expensive and least replaceable step is usually model generation.

Because of that:

- generation cannot be abstracted away as a trivial local transform
- verification sometimes can be delegated, but not always safely
- parsing / reshaping / tagging / slicing are often local and deterministic
- model-facing steps should be explicit gateway crossings

So the correct mental model is:

- local runtime does deterministic work
- gateway crossing does model work
- returned data is re-normalized into local runtime structures

## Worker classes

Typical worker roles:

- `generator`: synthesis, expansion, hard rewrite, creative generation
- `analyzer`: probe, extraction, classification, tail parsing, coverage checks
- `verifier`: optional stricter validation layer
- `vision`: optional multimodal interpretation gateway

These are not "objects with business logic".
They are endpoint classes with queueing and runtime behavior.

## Practical consequences

### 1. Do not model workers as heavy stateful DSL values

Instead of passing worker objects around, Atomic should use:

- role
- endpoint pool
- capacity
- queue state

### 2. Crossing a worker boundary is a meaningful event

Every gateway crossing should be treated as:

- a transform boundary
- a lineage boundary
- a benchmark point
- a metadata capture point

### 3. The local runtime stays responsible for safe structure

Workers should not be trusted to define storage layout.
They only help produce or classify content.
The local runtime must:

- normalize outputs
- preserve addressing
- preserve checkpoint structure
- preserve lineage

## Target runtime shape

The long-term worker model should look like:

- `role -> [endpoints]`
- endpoint queues
- explicit `gen_id`
- subscriptions by `gen_id`
- optional stop-next / preemption

## Summary

Atomic workers are best treated as gateways/endpoints.

The local runtime owns:

- memory
- tables
- addressing
- metadata
- checkpoints

The worker owns only:

- model execution
- endpoint-specific latency/capacity behavior
- returned raw artifact

