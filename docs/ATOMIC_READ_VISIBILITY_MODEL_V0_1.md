# Atomic Read Visibility Model v0.1

## Purpose

This document defines how read access should work inside Atomic.

The goal is:

- predictable context
- explicit visibility
- replayable reads
- no hidden global memory bleed

## Core rule

Read access in Atomic should be:

- hierarchical
- semantic
- time-aware

Meaning:

- what can be read depends on node position
- what can be read depends on data meaning and refs
- what can be read inside a branch depends on message order

## Main formula

The practical read set should be:

```text
visible_read_set =
  lineage scope
  + prior branch messages
  + explicit refs
```

## Hierarchical read

From a given node or message, it should always be possible to read:

- the `root-node`
- ancestor nodes
- declared checkpoint nodes in its lineage

This is the stable structural context.

## Branch-local read

Inside one discussion branch or action thread, read access should be one-directional.

You may read:

- earlier messages in the same branch

You may not read:

- later messages in the same branch

This keeps branch replay deterministic.

## Branch message model

Inside a branch, messages should be readable as:

- an ordered list of prior messages

Not:

- a mutable shared blob

This matters because a branch is still message-based, not state-magical.

## Checkpoint read

Checkpoint nodes should be readable from descendant work when they are part of the declared route.

That includes:

- raw carriers
- projection containers
- linked spans
- revision attachments

This is a controlled read surface, not a free-for-all memory dump.

## Explicit cross-branch access

Direct read access across branches should not happen implicitly.

Cross-branch data should only be readable through:

- explicit refs
- linked summaries
- linked containers
- promoted checkpoint artifacts

Meaning:

- sibling branches are not automatically visible
- future repair branches are not automatically visible
- arbitrary other threads are not automatically visible

## Semantic read

Read access should also work by semantic object type.

Examples:

- read carrier
- read table
- read span set
- read chunk set
- read checkpoint
- read revision summary

This is different from pure tree traversal.

The system should support both:

- structural location
- semantic object lookup

## Structural read

Structural read means:

- walk root
- walk parent chain
- walk declared child containers
- walk current branch history

This is topology-based access.

## Message read

Message read means:

- read prior messages as an ordered message list

This is especially important in:

- branch discussions
- comment threads
- local action sequences

## Semantic read

Semantic read means:

- resolve typed refs to the actual readable object

Examples:

- `current checkpoint carrier`
- `root task input`
- `previous response_table`
- `span thread for ref X`

This should still respect visibility boundaries.

## Example

Suppose there is:

- one root task node
- one checkpoint node
- one discussion branch under a marked span

Then a message inside that branch may read:

- root task input
- checkpoint carrier
- checkpoint projections
- earlier messages in the same branch

It may not read:

- later replies in the branch
- unrelated sibling branches
- hidden global runtime state

unless explicitly linked.

## Why this matters

Without explicit read visibility:

- context drifts
- replay breaks
- branches leak into each other
- agents overread irrelevant data

With this model:

- context is stable
- reads are explainable
- summaries and promotions become first-class

## Suggested terms

Useful terms for the system:

- `lineage scope`
- `branch prior messages`
- `explicit ref access`
- `semantic readable objects`
- `structural readable objects`

## Short summary

Atomic read access should be:

- hierarchical by lineage
- ordered within a branch
- semantic through typed refs
- restricted across branches unless explicitly linked

This gives a clean and replayable read model for message-based work.
