# Atomic Transfer Context

## Status

Atomic DSL is no longer just a pipeline syntax experiment.
It should be treated as the front-facing language of a local-first agent runtime.

The current direction is:

- memory-first architecture
- worker as gateway/endpoint, not as rich object
- gateway crossing as a meaningful semantic event
- fail-safe high-level agent layer
- checkpoints as explicit, redundant, serializable artifacts
- local user data as primary storage
- messages + sidecar metadata as source of truth
- matrix-first storage with sparse virtual file addressing for text chunks

## Hard project constraints

These constraints are non-optional:

1. all data, including intermediate data, must live as visible forum-like or card/chat-style objects
2. worker interaction must use the same visible system rather than hidden private buffers
3. the client must remain thin

Low-level stores may exist underneath, but they must link back to explicit visible `data_origin`.

## Core architectural stance

### 1. Memory-first

The runtime should optimize for:

- replayability
- recoverability
- inspectability
- deterministic local transforms
- robust checkpoint repair

Not for the theoretically fastest pipeline.

### 2. Worker is a gateway

`worker` in Atomic should mean:

- endpoint class
- queue boundary
- model execution surface

It should not mean:

- heavy stateful DSL object
- owner of memory
- owner of storage layout

The local runtime owns:

- memory
- addressing
- tables
- checkpoint structure
- lineage
- metadata normalization

### 3. Every gateway crossing is an event

For each crossing, preserve at minimum:

- `gen_id`
- lineage
- benchmark timing
- transform type
- checkpoint from/to
- source refs
- target refs
- possible fingerprint
- optional lazy embedding

This event is useful even before embeddings exist.

## Storage direction

Primary direction:

- local-first
- thin-client
- sandbox-by-default

Source of truth:

- messages
- sidecar metadata

Working representation:

- tables as default working format
- lists represented as matrices where possible
- text carried in marked carriers
- sparse virtual file address space for chunked text

For text spans, preserve redundant positional metadata:

- `char_start`
- `char_end`
- `char_len`
- optional token offsets

## Metadata linking

Metadata should be linkable by:

- pipeline lineage
- transform type
- checkpoint from/to
- source refs
- target refs

## Probe layer

Probe should live in the central runtime layer, not as an afterthought in workers.

Main probe families:

- `logprobe`
- `anti-repeat`
- `coverage`
- `contradiction`
- `implication`

`continue` should be modeled not as endless text extension, but as:

- checkpoint
- snapshot
- repair loop

## High-level agent layer

The high-level layer should stay intentionally blunt and fail-safe.

Minimal frame:

- what exists
- what we want
- constraints
- checkpoints
- edge cases

This layer should remain simpler than the storage/runtime layer.

## Retrieval/index stance

ChromaDB fits well as:

- retrieval layer
- indexing layer

But not as:

- source of truth
- canonical memory store

## Sharing boundary

Between users, we want to share:

- DSL
- presets
- schemas
- safe metadata summaries

But not:

- private internal memory
- local LLM core

Security rule:

- share the sandbox, not the core

## Benchmark anchor

`Task A` is the canonical benchmark for the current phase.

Definition:

- prompt -> 4 demoness blocks
- unique property group -> 1 demoness block

Uniqueness pressure at minimum on:

- eyes
- hair
- pose
- names

Why it matters:

- parse
- split
- assemble
- verify
- text-image alignment
- route comparison
- uniqueness failure analysis

## Practical implication for Atomic DSL

Atomic DSL should evolve as the user-visible orchestration layer over:

- local deterministic transforms
- explicit gateway crossings
- serialized checkpoints
- matrix-like intermediate forms
- repair-oriented continuation
- probe-driven verification

The DSL should stay:

- simple
- composable
- visually legible
- domain-friendly
- easy for models to generate
- redundant where redundancy reduces critical mistakes

Design preference:

- allow slightly verbose commands
- prefer explicit fields over compact clever syntax
- make critical mistakes hard to express
- separate runtime orchestration from prompt-construction concerns

Domain DSLs should be:

- small
- overlapping
- easy to inspect

## Overall product vector

This is not "yet another chat".

The target is:

- a local agentic NLP framework
- for ordinary users
- with strong storage semantics
- explicit checkpoints
- safe sandbox boundaries

## Files to read first

- `docs/ATOMIC_GATEWAY_MODEL.md`
- `docs/ATOMIC_GATEWAY_EMBEDDING_NOTES.md`
- `docs/TASK_A_DEMONESSES_BENCHMARK.md`
- `docs/PIPELINE_DSL_SPEC.md`
- `docs/ATOMIC_DSL_RECIPES.md`

## Immediate next-layer candidates

The next implementation layer should likely define:

1. canonical checkpoint schema
2. gateway event schema
3. sidecar metadata schema
4. matrix/text carrier schema
5. probe result schema
6. Task A reference pipeline in Atomic DSL
