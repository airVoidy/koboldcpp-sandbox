# Atomic AABB List Layout v0.1

## Purpose

This note fixes an important correction from the April 22, 2026 discussion:

there is **not** a strict textual notation for `[-1] / [0] / [+1]`.

Instead, the intended invariant is visual/layout-oriented:

- three AABB regions attached to a list/scope
- free mutation/reordering inside them
- consistent semantic role, not rigid syntax

So this is a UI/layout model, not a formal textual grammar.

## Core Model

For a list-like or scope-like view, provide three aligned AABB zones:

1. historical / previous side
2. current / active side
3. optimistic / next / shadow side

These may be thought of informally as:

- left
- center
- right

or as:

- previous
- current
- next

But the important invariant is spatial, not textual.

## Why AABB

AABB is useful because it gives:

- easy visual grouping
- simple drag/reorder/mutate behavior
- stable container geometry
- no need to over-formalize syntax too early

The user/agent can:

- move content around
- attach rules
- inspect shadow branches
- compare snapshots

without requiring a rigid line-based notation.

## Recommended semantics of the three regions

### Region A: Historical / Previous

Used for:

- prior snapshots
- older checkpoint instances
- inherited context
- already-resolved or archived forms

### Region B: Current / Active

Used for:

- active working selection
- current checkpoint
- editable structural view
- main projection focus

### Region C: Optimistic / Next / Shadow

Used for:

- speculative rules
- optimistic rollout
- branch alternatives
- unresolved future forms
- shadow projections

## Important clarification

These are not three separate object families.

They are:

- three layout regions
- over the same broader atomic playground

Objects, rules, and slots may appear in more than one region as related views.

## Cursor behavior

The discussion also kept one strong invariant:

- the active cursor is singular per active editor/agent view

So the three AABB regions do not imply multiple independent cursors.

Instead:

- one cursor
- multiple spatial regions
- multiple projection views

This is much closer to the intended UX.

## What this avoids

This layout model avoids:

- premature formal syntax
- overfitting to one textual notation
- confusion between spatial arrangement and semantic identity

It keeps the system open for:

- sparse catalogs
- grid/canvas views
- list views
- checkpoint editors
- structural editing with visual grouping

## Relation to older shorthand

Older shorthand like:

- `[-1]`
- `[0]`
- `[+1]`

may still be useful informally in notes.

But the actual invariant should be read as:

- three AABB zones with stable semantic roles

not as a required text-level notation.
