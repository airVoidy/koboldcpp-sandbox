# Atomic Memory / Revision Bridge v0.1

## Purpose

This document connects three Atomic directions into one stack:

- memory model
- schema model
- revision graph

The goal is to make it explicit how:

- visible data storage
- working matrix state
- checkpoints
- gateway events
- transparent versioning

fit together.

## The three documents

This bridge links:

- `ATOMIC_MEMORY_SPEC_V0_1.md`
- `ATOMIC_SCHEMA_DRAFT_V1.md`
- `ATOMIC_REVISION_GRAPH_SPEC_V0_1.md`

## Core stack

The intended stack is:

1. visible carrier or message layer
2. sidecar metadata layer
3. matrix working layer
4. checkpoint and gateway-event layer
5. revision graph layer
6. optional retrieval/index layer

These are not competing models.
They are different cuts through the same runtime.

## Practical stance

For now, Atomic may remain message-centric in practical storage.

That means:

- `MessageRecord` is a valid primary visible object
- `message_id` remains a normal anchor
- blocks, tables, checkpoints, and revisions can all attach to messages

This should be treated not only as a temporary convenience, but as a practical L1 rule:

- the top transparent layer remains message-based
- meaningful data changes should be wrappable into message containers
- other lower layers may be more specialized internally
- but they should still surface through message-level envelopes

At the same time, the more general canonical model should remain available:

- `DataOrigin`
- `CarrierBlock`
- generalized `carrier_ref`

So:

- message-centric = practical deployment view
- carrier-centric = generalized canonical view

## Main mapping

### Memory spec -> Schema draft

`MessageRecord`
maps roughly to:

- `DataOrigin`
- plus visible carrier body
- plus linked `SidecarMeta`

`TableFrame`
maps to:

- `MatrixFrame`

`SparseBlock`
maps to:

- `CarrierBlock`
- plus sparse virtual addressing metadata

`VirtualFileRegistry`
stays as:

- sparse virtual address registry

### Schema draft -> Revision graph

`Checkpoint`
maps to:

- semantic runtime boundary
- often paired with `SnapshotRef`
- often promoted into `RevisionCommit`

`GatewayEvent`
maps to:

- explicit attached event on a commit
- route/benchmark evidence
- lineage boundary

`ProbeResult`
maps to:

- revision evidence
- branch trigger
- acceptance or repair justification

`RouteRecord`
maps to:

- branch narrative
- commit-chain summary
- accepted-route label source

## Checkpoint vs revision

These two must stay separate.

`Checkpoint` means:

- semantic execution boundary
- parse/verify/repair stage marker
- replay/repair unit

`RevisionCommit` means:

- durable history node
- parent-linked graph state
- inspectable diff/snapshot point

Relationship:

- many checkpoints should produce commits
- not every small commit needs a major checkpoint

## Gateway events in the stack

Gateway crossing should not be reduced to hidden metadata.

The right relationship is:

1. worker call happens
2. `GatewayEvent` is created
3. output lands in visible carrier/message
4. sidecar + matrix projections may be created
5. checkpoint may be formed
6. revision commit records the accepted durable state

So `GatewayEvent` is not the commit.
It is a linked event that helps explain why the commit exists.

## Snapshots in the stack

`SnapshotRef` is the durable captured state of some bounded set of artifacts.

In practice, the snapshot usually bundles:

- message or carrier content
- blocks
- sidecar metadata
- matrix frames
- checkpoint refs

This is the main bridge between:

- checkpoint semantics
- revision durability

## Message-centric path

In a message-centric deployment, a normal path looks like:

1. `MessageRecord` created or edited
2. `SparseBlock` / block refs attached
3. `TableFrame` projection created
4. `GatewayEvent` recorded if model crossing happened
5. `Checkpoint` created for a stable stage
6. `SnapshotRef` captures bundle
7. `RevisionCommit` records the durable transition

In other words:

- lower layers may specialize storage
- but the user-facing operational envelope still remains message-first

## Carrier-centric generalized path

In a generalized carrier deployment, the path is the same, but `message_id` broadens into:

- `carrier_ref`
- `data_origin_ref`

Messages are then one carrier type among:

- chat messages
- cards
- forum posts
- thread blocks

## Prompt factories and revisioning

Prompt factories stay outside core runtime orchestration, but they still affect behavior.

So the stack should treat them as:

- versioned artifacts
- branchable artifacts
- route-affecting artifacts

Typical relationship:

- a route commit may reference one or more prompt-factory revisions
- changing `context`, `instruction`, `think`, or `format` can justify a new branch

## What should be inspectable together

For any accepted state, the user should be able to inspect:

- visible message/carrier
- related blocks
- current matrix projection
- checkpoint status
- gateway events
- probe results
- revision diff / parent chain

This is the minimum transparency promise.

## Suggested UI implication

The UI should eventually allow pivoting one artifact through multiple views:

- visible message view
- block view
- matrix view
- checkpoint view
- gateway event view
- history view

All of these are views over the same connected runtime graph.

## Minimal invariant set

The combined stack should preserve these invariants:

1. visible data remains the source of truth surface
2. every durable artifact links to visible origin data
3. every model crossing creates a `GatewayEvent`
4. every meaningful replay boundary creates a `Checkpoint`
5. every durable accepted change can be represented as a `RevisionCommit`
6. every rollback remains visible as graph history
7. prompt-factory changes are versionable, not hidden
8. meaningful durable changes remain representable through message-layer containers

## Recommended implementation order

The safest order is:

1. message/block + sidecar foundations
2. matrix projections
3. checkpoint objects
4. gateway-event objects
5. revision commits + snapshots + patches
6. branch/tag/rollback support
7. prompt-factory revision linking

## Short summary

The intended relationship is:

- memory spec explains where data lives
- schema draft explains what object types exist
- revision graph explains how changes become transparent durable history

Together they define a local-first Atomic runtime that is:

- readable
- addressable
- checkpointed
- benchmarkable
- versioned without magic
