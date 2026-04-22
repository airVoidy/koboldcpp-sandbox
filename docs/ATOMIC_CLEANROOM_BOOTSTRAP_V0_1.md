# Atomic Clean-Room Bootstrap v0.1

## Purpose

This is a clean-room starting point for a new project.

It does **not** depend on:

- `wip/atom_prototype`
- `koboldcpp-sandbox`
- previous wrapper implementations

It keeps only the invariants that survived the design discussion.

## Core Model

The system is built from four primary entities:

1. `AtomicObject`
2. `AtomicList`
3. `AtomicRule`
4. `ProjectionSlot`

Everything else is derived.

## 1. AtomicObject

`AtomicObject` is the main runtime carrier.

It is:

- a dynamic object wrapper
- valid for real runtime instances
- valid for virtual types
- valid for detached structural points
- valid for shadow objects

It does not try to distinguish too early between:

- field
- method
- declaration
- bind
- computed projection

Those distinctions live in attached rules and in projection views.

Minimal shape:

```ts
type AtomicObject = {
  id: string
  data: JsonValue
  out?: JsonValue
  refs?: AtomicRef[]
}
```

Notes:

- `id` is a stable internal identity
- `data` is the current canonical carrier
- `out` is the latest materialized result if needed
- `refs` are optional external or local references with side metadata

## 2. AtomicList

`AtomicList` is the general grouping primitive.

It is not "just an array".

It is used for:

- hierarchical grouping
- detached collections
- dedup-oriented collections
- scope assembly
- virtual grouping without forced instance naming

Minimal shape:

```ts
type AtomicList = {
  id: string
  items: string[]
  mode?: 'ordered' | 'dedup' | 'scope'
  refs?: AtomicRef[]
}
```

Important:

- many runtime objects can exist only because they are wrapped by a list/scope
- a list may act as a virtual container without owning concrete payload

## 3. AtomicRule

`AtomicRule` is any attached rule-like thing.

This intentionally merges:

- type declarations
- methods
- structural projections
- functional projections
- computed transforms
- binds
- shadow hints

The distinction between these is runtime-relative and should not be forced into separate root primitives.

Minimal shape:

```ts
type AtomicRule = {
  id: string
  body: JsonValue
  refs?: AtomicRef[]
}
```

The runtime classifies a rule by how it is used, not by a required static enum.

## 4. ProjectionSlot

`ProjectionSlot` is the key UI/runtime primitive.

The slot does **not** need to store a value first.

Instead it may first store:

- projection vector
- rule reference
- transform description
- checkpoint relation

Only later does it materialize a value.

Stages:

1. declared
2. resolving
3. materialized
4. shadow/problem

Minimal shape:

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

This lets the interface show:

- how something will be computed
- before the value exists

That is the main visual invariant.

## Atomic Layers

The runtime should keep four logical layers.

### 1. Type Metadata Layer

What was encountered and to which atomic types it was decomposed.

### 2. Structural Projection Layer

How to compose and display objects/scopes/lists.

### 3. Functional Projection Layer

Which rules transform one form into another.

### 4. Transition Virtualization Layer

How a transition is split into dumb atomic instrumentable steps.

These are layers of interpretation, not separate object families.

## Hashing

`hash` is not a base field of `AtomicObject`.

Instead:

- artifact hashes are produced by rules or rulesets
- they are projection-relative
- they may be compact binary/string artifacts
- they may later be decoded into human-readable views

Minimal artifact form:

```ts
type AtomicArtifact = {
  id: string
  source: string
  blob: string
  view?: JsonValue
}
```

This keeps machine traces separate from visible runtime state.

## Clean-Room Runtime

The new project should expose only a few gestures:

```ts
putObject(object)
putList(list)
attachRule(targetId, rule)
declareSlot(slot)
materializeSlot(slotId)
snapshot(targetId)
```

Everything else can be built on top.

## Recommended Invariants

1. `AtomicObject` remains minimal.
2. `AtomicList` is the only general grouping primitive.
3. `AtomicRule` remains untyped at the root level.
4. `ProjectionSlot` is where computation becomes visible.
5. Hashes/artifacts are projection outputs, not object identity fields.
6. Runtime and structural projections are different layers.
7. Shadow branches live as parallel slot/object views, not as a separate graph explosion.

## What This Avoids

This clean-room model intentionally avoids:

- hard dependency on previous wrapper names
- premature distinction between method and non-method
- forcing all semantics into one universal wrapper schema
- treating virtual types as ordinary payload instances
- storing every materialized instance permanently

## Migration Note

If old concepts are imported later, map them into this layer carefully:

- `VirtualObject` may become `AtomicObject`
- `VirtualList` may become `AtomicList`
- runtime or projection declarations may become `AtomicRule`
- UI/runtime cells should become `ProjectionSlot`

But the new project should start without assuming those old meanings are already correct.
