# Atomic Object Map v0.1

## Purpose

This document is the compact object map for the current Atomic direction.

It summarizes:

- the main object types
- their roles
- their main links
- how they fit into one runtime graph

It is meant as a practical reference for:

- architecture work
- UI design
- storage design
- runtime implementation
- benchmark routing

## Core stack

Atomic currently has these practical layers:

1. `L1 Message Layer`
2. sidecar metadata layer
3. matrix working layer
4. checkpoint and gateway-event layer
5. revision graph layer
6. optional retrieval/index layer

Important invariant:

- `L1` remains canonically message-based
- even if lower storage is implemented differently
- meaningful durable changes should still surface through message containers

## Main object families

The current minimum set is:

1. `MessageRecord`
2. `DataOrigin`
3. `CarrierBlock`
4. `SidecarMeta`
5. `TableFrame` / `MatrixFrame`
6. `TextSpan`
7. `Checkpoint`
8. `GatewayEvent`
9. `ProbeResult`
10. `RouteRecord`
11. `RevisionCommit`
12. `RevisionPatch`
13. `SnapshotRef`
14. `BranchRef`
15. `TagRef`
16. `MergeRef`
17. `ConflictRef`
18. `RollbackRef`
19. `PromptFactory`
20. `AtomicMacro`

## 1. MessageRecord

Role:

- practical `L1` visible container
- primary user-facing message envelope

Owns or carries:

- readable text
- structured readable body
- sidecar metadata links
- block references

Main refs:

- `message_id`
- `block_refs`
- `meta_refs`
- `checkpoint_refs`
- `revision_refs`

## 2. DataOrigin

Role:

- generalized canonical origin type
- broader abstraction above message/card/forum/chat carrier kinds

Examples:

- message
- card
- forum post
- thread block

Main refs:

- `origin_id`
- `origin_kind`
- `container_ref`

Relationship to `MessageRecord`:

- `MessageRecord` is one practical `DataOrigin` form

## 3. CarrierBlock

Role:

- addressable block inside visible carrier/message

Used for:

- text chunks
- sections
- tables
- DSL snippets
- benchmark blocks

Main refs:

- `block_id`
- `data_origin_ref`
- `char_start`
- `char_end`
- `char_len`

## 4. SidecarMeta

Role:

- machine-friendly metadata attached to visible data

Used for:

- parse annotations
- transform metadata
- lineage links
- checkpoint links
- probe links

Main refs:

- `meta_id`
- `data_origin_ref`
- `carrier_block_ref`
- `source_ref`
- `target_ref`

## 5. TableFrame / MatrixFrame

Role:

- canonical working representation
- normalized matrix/table layer

Used for:

- lists
- constraints
- accepted/rejected rows
- probe tables
- benchmark projections

Main refs:

- `frame_id` or `matrix_id`
- `message_refs`
- `row_origin_refs`
- `storage_ref`

Rule:

- if an artifact survives longer than one step, it should usually have a matrix projection

## 6. TextSpan

Role:

- precise positional text mapping

Used for:

- extracted values
- aligned annotations
- block-local addressing

Main refs:

- `span_id`
- `data_origin_ref`
- `carrier_block_ref`
- `char_start`
- `char_end`
- `char_len`

## 7. Checkpoint

Role:

- semantic runtime boundary
- replay and repair unit

Used for:

- parse stage boundary
- verify stage boundary
- continue/repair boundary

Main refs:

- `checkpoint_id`
- `data_origin_ref`
- `carrier_block_refs`
- `parent_checkpoint_refs`
- `artifact_refs`

Important:

- checkpoint is not the same as revision commit

## 8. GatewayEvent

Role:

- one explicit crossing into a worker endpoint
- lineage and benchmark event

Used for:

- generation
- analysis
- verification
- multimodal interpretation

Main refs:

- `event_id`
- `gen_id`
- `checkpoint_from`
- `checkpoint_to`
- `input_refs`
- `output_refs`

Important:

- every meaningful worker crossing should produce `GatewayEvent`
- accepted output should still surface through message/container representation

## 9. ProbeResult

Role:

- explicit runtime probe artifact

Probe families:

- `logprobe`
- `anti-repeat`
- `coverage`
- `contradiction`
- `implication`

Main refs:

- `probe_id`
- `target_ref`
- `input_refs`
- `lineage_ref`

## 10. RouteRecord

Role:

- high-level run/route spine

Used for:

- route replay
- route comparison
- accepted route labeling

Main refs:

- `route_id`
- `checkpoint_refs`
- `gateway_event_refs`
- `probe_refs`
- `dsl_ref`

## 11. RevisionCommit

Role:

- durable history node in revision graph

Used for:

- transparent versioning
- accepted state capture
- rollback-safe history

Main refs:

- `commit_id`
- `parent_commit_refs`
- `checkpoint_ref`
- `gateway_event_refs`
- `patch_refs`
- `snapshot_ref`

## 12. RevisionPatch

Role:

- inspectable change record between revisions

Used for:

- text changes
- matrix changes
- sidecar updates

Main refs:

- `patch_id`
- `commit_ref`
- `target_refs`

## 13. SnapshotRef

Role:

- recoverable bounded snapshot of state

Used for:

- replay
- compare
- rollback

Main refs:

- `snapshot_id`
- `commit_ref`
- `included_refs`
- `storage_ref`

## 14. BranchRef

Role:

- alternate route or repair path in revision graph

Main refs:

- `branch_id`
- `base_commit_ref`
- `head_commit_ref`
- `branch_kind`

## 15. TagRef

Role:

- stable label over revision or checkpoint state

Examples:

- accepted
- benchmark pass
- published preset
- rollback safe

Main refs:

- `tag_id`
- `target_commit_ref`
- `tag_kind`

## 16. MergeRef

Role:

- explicit merge of revision branches

Main refs:

- `merge_id`
- `commit_ref`
- `source_branch_refs`

## 17. ConflictRef

Role:

- explicit unresolved or resolved merge/replay conflict

Main refs:

- `conflict_id`
- `left_commit_ref`
- `right_commit_ref`
- `target_ref`

## 18. RollbackRef

Role:

- explicit record of return to an earlier stable state

Main refs:

- `rollback_id`
- `from_commit_ref`
- `to_commit_ref`

## 19. PromptFactory

Role:

- separate prompt-construction layer
- not the same as runtime orchestration

Must make explicit:

- `context`
- `instruction`
- `think`
- `format`
- optional `examples`
- optional `policy`

Main refs:

- `prompt_factory_id`
- `revision_ref`
- `input_schema_ref`
- `output_schema_ref`

Important:

- prompt factories should be versioned
- prompt factories may affect route behavior

## 20. AtomicMacro

Role:

- reusable Atomic DSL building block

Used for:

- saved route fragments
- benchmark recipes
- standard transforms

Main refs:

- `macro_id` or `name`
- `dsl_ref`
- `input_refs`
- `output_refs`
- `revision_ref`

## Main relation graph

The most common runtime relationship is:

`MessageRecord`
-> `CarrierBlock`
-> `SidecarMeta`
-> `TableFrame / MatrixFrame`
-> `Checkpoint`
-> `GatewayEvent`
-> `ProbeResult`
-> `RevisionCommit`
-> `SnapshotRef`

And across time:

`RevisionCommit`
-> `BranchRef`
-> `MergeRef` / `ConflictRef` / `RollbackRef`

And for orchestration inputs:

`PromptFactory`
-> worker-facing payload
-> `GatewayEvent`

`AtomicMacro`
-> `RouteRecord`
-> `Checkpoint` / `RevisionCommit`

## Typical object path

For a normal parse/generate/verify flow:

1. user creates or edits `MessageRecord`
2. runtime derives `CarrierBlock`
3. local transform creates `TableFrame`
4. worker crossing creates `GatewayEvent`
5. verification creates `ProbeResult`
6. stable stage creates `Checkpoint`
7. durable accepted state creates `RevisionCommit`
8. commit stores or links `SnapshotRef`

## Message-first invariant

Even when lower implementation layers are more specialized:

- user-facing durable data should still surface through `MessageRecord`
- checkpoint-worthy state should be representable as message content
- gateway outputs should attach to message-level containers
- revisions should be explainable through message-level artifacts

This keeps the system:

- transparent
- interoperable with other modules
- convenient for ordinary users

## Distinctions that must not collapse

These pairs must stay distinct:

- `MessageRecord` vs `SidecarMeta`
- `CarrierBlock` vs `TextSpan`
- `Checkpoint` vs `RevisionCommit`
- `GatewayEvent` vs `RevisionCommit`
- `PromptFactory` vs `AtomicMacro`
- `RouteRecord` vs `BranchRef`

## Minimal implementation set

If implementation must start small, start with:

1. `MessageRecord`
2. `CarrierBlock`
3. `SidecarMeta`
4. `TableFrame`
5. `Checkpoint`
6. `GatewayEvent`
7. `RevisionCommit`
8. `RevisionPatch`
9. `SnapshotRef`
10. `PromptFactory`

That is enough to make the system:

- message-first
- matrix-capable
- checkpoint-aware
- gateway-aware
- transparently versioned

## Short summary

Atomic is best understood as one connected graph where:

- messages are the canonical transparent surface
- blocks and sidecars make them addressable
- matrices make them operational
- checkpoints make them replayable
- gateway events make model crossings explicit
- revisions make all durable changes transparent
- prompt factories and macros make orchestration reusable without hidden magic
