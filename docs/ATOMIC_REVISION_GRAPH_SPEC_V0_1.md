# Atomic Revision Graph Spec v0.1

## Purpose

`Atomic` needs a transparent internal revision system for data.

The goal is not to mimic developer Git UX exactly.
The goal is to make all meaningful data changes and route changes:

- visible
- replayable
- auditable
- branchable
- mergeable
- recoverable

without hidden magic.

This layer should work for:

- visible messages
- card/chat carriers
- blocks inside carriers
- sidecar metadata
- table projections
- checkpoints
- gateway-produced outputs

## Design stance

This is a data revision graph, not a code VCS clone.

It should behave like an internal Git-like substrate in the following sense:

- every meaningful state may be committed
- commits form a parent-linked graph
- alternate routes may branch
- repair flows may fork
- accepted states may be tagged
- diffs and snapshots must be inspectable

But it should stay native to Atomic concepts:

- message-centric or carrier-centric data
- checkpoint-driven execution
- gateway events
- probe results
- route comparison

## Core rule

No durable mutation should become untraceable.

If visible data or linked sidecar state changes in a meaningful way, the system should be able to answer:

- what changed
- when it changed
- why it changed
- what produced the change
- which prior state it came from
- whether the change was accepted

## Conceptual mapping

The rough Git-like mapping is:

- commit -> revision commit
- tree snapshot -> checkpoint snapshot
- patch -> revision patch
- branch -> route branch
- tag -> route/checkpoint label
- merge commit -> merge revision
- stash / working tree -> local mutable working state

## Main objects

The minimum graph objects are:

1. `RevisionCommit`
2. `RevisionPatch`
3. `SnapshotRef`
4. `BranchRef`
5. `TagRef`
6. `MergeRef`
7. `ConflictRef`
8. `RollbackRef`

## 1. RevisionCommit

Represents one durable revision point.

```json
{
  "commit_id": "rev_00042",
  "parent_commit_refs": ["rev_00041"],
  "branch_ref": "branch_task_a_main",
  "data_origin_refs": ["msg_00017", "blk_0012"],
  "checkpoint_ref": "ckp_task_a_parse_03",
  "gateway_event_refs": ["gwe_0042"],
  "probe_refs": ["probe_cov_08"],
  "patch_refs": ["patch_00042a"],
  "snapshot_ref": "snap_00042",
  "message": "Parsed demoness blocks into normalized uniqueness table",
  "producer": {
    "kind": "runtime_transform",
    "id": "normalize_constraints"
  },
  "status": "accepted",
  "created_at": "2026-03-27T19:10:00+03:00"
}
```

Rules:

- every durable state boundary may create a commit
- commits should be cheap enough to create often
- a commit may refer to one or many visible data origins
- commits are graph nodes, not only log lines

## 2. RevisionPatch

Represents the change between parent and child state.

```json
{
  "patch_id": "patch_00042a",
  "commit_ref": "rev_00042",
  "patch_kind": "structured_edit",
  "target_refs": ["msg_00017", "tbl_constraints_01"],
  "ops": [
    {
      "op": "append_block",
      "target": "msg_00017",
      "block_ref": "blk_0013"
    },
    {
      "op": "create_table_frame",
      "target": "tbl_constraints_01"
    }
  ],
  "summary": "Added parsed axiom block and created normalized constraint table"
}
```

Rules:

- patches should be inspectable by humans
- patch ops may be coarse-grained in `v0.1`
- patch detail may be richer for text spans, tables, and sidecars later

## 3. SnapshotRef

Represents a full or bounded snapshot of state at commit time.

```json
{
  "snapshot_id": "snap_00042",
  "commit_ref": "rev_00042",
  "snapshot_kind": "checkpoint_bundle",
  "included_refs": [
    "msg_00017",
    "blk_0012",
    "blk_0013",
    "tbl_constraints_01",
    "meta_parse_03"
  ],
  "storage_ref": "sidecar://snapshots/snap_00042.json"
}
```

Rules:

- snapshots are for replay, comparison, and rollback
- not every UI edit must force a heavy snapshot
- every checkpoint-worthy state should have a recoverable snapshot path

## 4. BranchRef

Represents an alternate route through the revision graph.

```json
{
  "branch_id": "branch_task_a_repair_pose_uniqueness",
  "base_commit_ref": "rev_00039",
  "head_commit_ref": "rev_00045",
  "branch_kind": "repair_route",
  "reason": "Pose uniqueness probe failed on main route",
  "status": "active"
}
```

Rules:

- branches are normal for route exploration
- repair loops should usually branch rather than mutate history invisibly
- accepted routes may later merge or remain as alternates

## 5. TagRef

Represents a stable label on a revision or checkpoint.

```json
{
  "tag_id": "tag_task_a_benchmark_pass",
  "target_commit_ref": "rev_00045",
  "tag_kind": "benchmark_accept",
  "label": "Task A accepted route v1"
}
```

Useful tag families:

- accepted
- benchmark
- published
- preset_seed
- rollback_safe

## 6. MergeRef

Represents convergence of two revision branches.

```json
{
  "merge_id": "merge_00007",
  "commit_ref": "rev_00050",
  "source_branch_refs": [
    "branch_task_a_main",
    "branch_task_a_repair_pose_uniqueness"
  ],
  "strategy": "explicit_selective_merge",
  "result": "accepted"
}
```

Rules:

- merges should remain explicit
- automatic merge may exist for simple sidecar/table changes
- text-carrier merges should be conservative

## 7. ConflictRef

Represents unresolved or resolved incompatibility during merge or replay.

```json
{
  "conflict_id": "conf_00003",
  "left_commit_ref": "rev_00048",
  "right_commit_ref": "rev_00049",
  "target_ref": "blk_0013",
  "conflict_kind": "text_span_overlap",
  "summary": "Both branches rewrote the same demoness block differently",
  "status": "unresolved"
}
```

Rules:

- conflicts should be first-class, not hidden exceptions
- unresolved conflicts should block silent merge acceptance

## 8. RollbackRef

Represents an intentional move back to an earlier stable state.

```json
{
  "rollback_id": "rb_00002",
  "from_commit_ref": "rev_00051",
  "to_commit_ref": "rev_00045",
  "reason": "Verifier route regressed uniqueness acceptance",
  "created_at": "2026-03-27T19:16:00+03:00"
}
```

Rules:

- rollback must itself be recorded
- rollback is not deletion of history
- rollback is a graph event

## Working state

The system should also maintain a local mutable working state.

This is the space for:

- unsaved text edits
- partially assembled matrices
- in-progress route construction
- UI-local rearrangements

But once a change becomes checkpoint-relevant, benchmark-relevant, or user-meaningful, it should become commit-visible.

## Revision triggers

The system should create or strongly suggest commits on:

- checkpoint creation
- gateway crossing result acceptance
- probe-triggered repair branch start
- explicit user save
- visible message/card mutation
- macro or DSL route publication

## What should be versioned

At minimum:

- visible carrier content
- carrier blocks
- sidecar metadata
- matrix frames
- checkpoint bundles
- route definitions
- prompt-factory definitions
- macro definitions

Optional later:

- grammar presets
- schema presets
- benchmark manifests

## What a commit is attached to

Every commit should link to one or more Atomic-native anchors:

- `message_id`
- `carrier_ref`
- `block_ref`
- `checkpoint_ref`
- `gateway_event_ref`
- `probe_ref`
- `route_ref`

This is why the revision graph remains transparent.
It is not versioning an invisible object heap.
It is versioning inspectable user-facing or runtime-facing artifacts.

## Revision transparency rule

The user should be able to inspect:

- current head
- parent chain
- branch points
- diff summary
- rollback path
- accepted tags

without needing developer tooling.

This suggests UI views such as:

- history panel
- branch graph
- checkpoint compare
- message/block diff
- route diff

## Diff policy

Different artifact kinds need different diff modes.

Recommended modes:

- text diff for message bodies and blocks
- row diff for matrix frames
- field diff for sidecar metadata
- edge diff for route graphs
- event diff for gateway/probe histories

`v0.1` does not need perfect semantic diffing.
It needs inspectable and stable diffing.

## Branch policy

Branches should be cheap.

That matters because Atomic is explicitly exploring:

- alternate routes
- repair loops
- verification retries
- prompt-factory variants
- parse strategies

If branching is too heavy, users and agents will fall back to hidden overwrite behavior.

## Merge policy

Default merge behavior should be conservative.

Safe auto-merge candidates:

- append-only metadata
- independent sidecar additions
- non-overlapping matrix rows
- non-overlapping carrier blocks

Unsafe auto-merge candidates:

- overlapping text rewrites
- contradictory probe verdicts
- competing checkpoint promotions
- competing accepted-route tags

## Relation to checkpoints

Checkpoint and revision are related but not identical.

- checkpoint = semantic/runtime boundary
- revision commit = durable graph state capture

Many checkpoints should produce commits.
Not every tiny commit must imply a major checkpoint.

## Relation to gateway events

Gateway events should not be buried in commit messages.

They should remain explicit linked objects.

A revision commit may:

- record acceptance of a gateway output
- attach a gateway event ref
- promote gateway output into visible carrier state

This is important for benchmark replay and route mining.

## Relation to prompt factories

Prompt factories should also be versioned.

That matters because route behavior can change not only from DSL changes, but from:

- `context` changes
- `instruction` changes
- `think` policy changes
- format contract changes

So prompt-factory revisions should be part of the same graph or a tightly linked sibling graph.

## Relation to message-centric vs carrier-centric views

This graph should support both:

- message-centric practical storage
- carrier/data-origin-centric generalized storage

In a message-centric deployment:

- commits may point mainly to `message_id`
- blocks and sidecars remain children

In a carrier-centric deployment:

- commits may point to generic `carrier_ref`
- messages become one carrier kind among others

## Suggested minimal commit message frame

Each commit should preferably summarize:

- what changed
- why
- produced by whom/what
- accepted or not

Minimal form:

```text
normalize constraints table
producer: analyzer + local transform
status: accepted
```

## Initial implementation milestone

The first usable milestone should implement:

1. `RevisionCommit`
2. `RevisionPatch`
3. `SnapshotRef`
4. `BranchRef`
5. `TagRef`
6. diff views for text and tables
7. rollback record

That is enough to make data history transparent without requiring a full merge engine.

## Design goal

The goal of `Atomic Revision Graph v0.1` is:

- transparent versioning
- no hidden data mutations
- branchable route exploration
- recoverable repair loops
- explicit accepted states
- inspectable history for ordinary users

In short:

an internal Git-like graph for Atomic data,
without turning Atomic into developer-only tooling.
