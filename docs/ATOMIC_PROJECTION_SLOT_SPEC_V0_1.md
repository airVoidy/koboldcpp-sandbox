# Atomic Projection Slot Spec v0.1

## Purpose

This note extracts one of the strongest conclusions from the April 22, 2026 discussion:

- a cell/slot should not first be modeled as a place that stores a value
- it should first be modeled as a place where a projection is declared and resolved

This makes the interface and the runtime much more inspectable.

## Core Principle

A projection slot exists before its value exists.

The slot may already contain:

- projection vector
- rule references
- transform description
- checkpoint relation
- shadow/problem status

The actual payload value is only one possible later state.

## Why this matters

If the UI shows only values, then:

- unresolved computation is invisible
- shadow alternatives become awkward
- users and agents cannot inspect how a value will be produced

If the UI shows slots first, then:

- a missing value is still meaningful
- the route to materialization is visible
- shadow/problem states are natural
- debug and branch inspection become much easier

## Slot Lifecycle

Recommended states:

1. `declared`
2. `resolving`
3. `materialized`
4. `shadow`
5. `problem`

Meaning:

- `declared`: slot exists as an intended projection point
- `resolving`: rules and dependencies are being applied
- `materialized`: slot has a usable payload value
- `shadow`: alternate or speculative value path
- `problem`: failed or mismatched path

## Minimal Shape

```ts
type ProjectionSlot = {
  id: string
  owner: string
  vector: JsonValue
  ruleRefs?: string[]
  value?: JsonValue
  state: 'declared' | 'resolving' | 'materialized' | 'shadow' | 'problem'
}
```

Where:

- `owner` = the atomic object/list/scope that owns the slot
- `vector` = description of where the slot points and how it should be assembled
- `ruleRefs` = attached rules relevant for this slot
- `value` = only present after materialization

## Distinction from ordinary fields

A slot is not just a field.

A field usually answers:

- what value is here

A slot answers:

- what should be here
- by which projection
- by which rule
- in which state of resolution

So projection slots are much better suited for:

- atomic UI
- shadow branches
- checkpoint debugging
- explanation of runtime assembly

## Recommended UI behavior

By default, a slot should show:

- target/vector summary
- current state
- attached rule count or primary rule summary

And only optionally:

- fully materialized value
- expanded metadata
- shadow comparisons

This keeps the interface focused on computation structure, not only on payload snapshots.
