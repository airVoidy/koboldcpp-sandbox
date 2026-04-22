# Atomic Clean-Room Architecture — Session Notes 2026-04-22

## Purpose

This document summarizes the architectural conclusions from the April 22, 2026 discussion.

It is intentionally **descriptive first**:

- it does not try to prematurely lock the implementation
- it preserves the distinctions that matter in runtime semantics
- it avoids collapsing everything into one wrapper too early

This document is intended as a handoff/reference for a **new parallel project**, not as a patch against the old one.

---

## Related References

These older references remain useful, but must now be read with stronger disclaimers about scope and terminology drift:

- [ATOMIC_TWO_LINES_REFERENCE_V0_1.md](C:\llm\KoboldCPP agentic sandbox\docs\ATOMIC_TWO_LINES_REFERENCE_V0_1.md:1)
- [ATOMIC_OBJECT_UNIVERSAL_V0_1.md](C:\llm\KoboldCPP agentic sandbox\docs\ATOMIC_OBJECT_UNIVERSAL_V0_1.md:1)
- [ATOMIC_VIRTUAL_CONTAINER_ARCHITECTURE_DRAFT_V0_1.md](C:\llm\KoboldCPP agentic sandbox\docs\ATOMIC_VIRTUAL_CONTAINER_ARCHITECTURE_DRAFT_V0_1.md:1)
- [ATOMIC_CLEANROOM_BOOTSTRAP_V0_1.md](C:\llm\KoboldCPP agentic sandbox\docs\ATOMIC_CLEANROOM_BOOTSTRAP_V0_1.md:1)
- [SESSION_NOTES_VIRTUAL_CONTAINER_2026_04_18.md](C:\llm\KoboldCPP agentic sandbox\docs\SESSION_NOTES_VIRTUAL_CONTAINER_2026_04_18.md:1)
- [SESSION_SUMMARY_2026-04-18.md](C:\llm\KoboldCPP agentic sandbox\wip\SESSION_SUMMARY_2026-04-18.md:1)

Important:

- similar names across these documents do **not** imply identical runtime semantics
- some old documents describe wrappers/catalogs
- newer discussion is much more careful about runtime meaning, projection layers, and virtuality

---

## Executive Summary

The new Atomic direction should be modeled as a **layered projection/orchestration system**, not as:

- a single universal wrapper with one canonical meaning
- a classic object model
- a linear workflow engine

The key idea is:

- runtime semantics matter
- wrapper schemas are secondary
- projections are first-class
- shadow and virtual layers are not hacks, but part of the core model

The strongest current formulation is:

1. `AtomicObject` is the main dynamic runtime carrier.
2. `AtomicList` is the main grouping and scope primitive.
3. `AtomicRule` represents attached declarations/transforms/method-like things without forcing a hard split between them.
4. `ProjectionSlot` is the main visible computation unit in the interface.

The system should prefer:

- local scopes
- local projection-relative hashes/artifacts
- field-level decomposition where needed
- lazy materialization of runtime views
- strong distinction between structural and runtime projections

---

## 1. Main Correction to Older Docs

One of the most important conclusions from today's discussion:

The older universal-wrapper framing is too aggressive if read literally.

In particular, this kind of claim is no longer accurate as a primary truth:

> every previous shape collapses to one canonical wrapper

That is too strong.

Why:

- wrappers/catalog entries do not erase runtime semantics
- `VirtualObject`, `RefObject`, `AtomicRuntimeObject`, `VirtualList`, `ExecScope` do not live on the same semantic layer
- some are dynamic runtime carriers
- some are virtual type forms
- some are reference-resolved instances
- some are grouping/scoping mechanisms

So the correct stance is:

- many shapes may be **represented** through a wrapper
- but they do **not** collapse semantically into that wrapper

This is one of the main reasons a clean-room architecture is useful now.

---

## 2. Atomic Objects

### Definition

`AtomicObject` should be treated as a **full dynamic object wrapper**.

This includes:

- real runtime instances
- virtual runtime forms
- detached structural points
- shadow objects
- projected object views

The important part is that `AtomicObject` is not merely a catalog record.

It is a live runtime-facing carrier.

### Minimal shape

For the clean-room start, the object should remain minimal:

```ts
type AtomicObject = {
  id: string
  data: JsonValue
  out?: JsonValue
  refs?: AtomicRef[]
}
```

Why minimal:

- too much structure in the base object causes premature ontology lock-in
- old designs overloaded `type`, `kind`, `tags`, `hash`, `meta`
- those distinctions are often contextual and projection-relative

### Important invariant

An object may be:

- runtime
- atomic
- virtual
- projected

all at once, depending on which layer you are reading it from.

So the new model must never force these into mutually exclusive root classes too early.

---

## 3. Atomic Lists

`AtomicList` should be treated as a central abstraction, not as a convenience collection.

It is used for:

- scope assembly
- hierarchical grouping
- detached collections
- dedup-aware grouping
- virtual grouping
- fallback existence wrapper for objects that otherwise have no explicit outer carrier

This is especially important historically:

- many object forms only became operational because they were implicitly wrapped by a virtual list-like scope

### Important clarification

`VirtualList` in the older designs was not “just another object”.

It was strong precisely because it was so flexible:

- alias-path based
- relative-path based
- dedup based
- array-type based
- field-name based

This made it an extremely useful detached abstraction.

So the new project should preserve that power, but under a cleaner naming and layering scheme.

---

## 4. Virtual Objects vs Runtime Instances

This distinction must be preserved more carefully than in previous docs.

### Virtual Object

A virtual object is not primarily an instance payload.

It is closer to:

- a type-like runtime form
- a virtualized object shape
- a structural/runtime carrier without a concrete instance payload of its own

### Runtime Object

A runtime object is an actual instantiated carrier in the running system.

### Ref Object

A `RefObject` is not “still virtual”.

It is usually a **real runtime instance** whose values are resolved through a reference to another object's cached resolve path.

That makes it operationally real, even if its values are fetched lazily.

### AtomicRuntimeObject

Historically:

- before JSONL or other SoT burial, the object is just a live runtime object
- after serialization/reference burial, it is still that runtime object
- but it also becomes reference-addressable

So:

- serialization does not destroy the runtime object
- it only adds another mode of addressability

---

## 5. Source of Truth

Another important refinement:

`Source of Truth` is contextual.

It is often **not** simply:

- the incoming payload
- nor a single field

In practice:

- some modules should treat incoming packets as transient
- information should often be relocated into more suitable data structures
- the authoritative source depends on query, module, and projection context

So Atomic should be able to:

- keep several candidate source projections
- answer which source is authoritative for a given query
- route from old sources to current projections
- preserve lineage

This means:

- `SoT` is not a single root object
- it is a queryable stance over the orchestration layer

---

## 6. Fields and Field Context

Fields remain important, but they are not sufficient on their own.

### Why not

A field is too fragile and too context-dependent.

It behaves more like:

- a cell in a row
- a header/value fragment
- a container-slot/value pair

It rarely carries full meaning by itself.

### Practical conclusion

What matters more operationally is:

- field-in-context
- field plus parent/schema/virtual-type relationship

This is why field projections and field cuts are useful, but fields alone should not be mistaken for full semantic units.

### Stronger decomposition idea

A useful clean-room idea from today:

- even field name and field value may be decomposed into canonical atomic pieces
- this can give a more uniform detached form

This remains a design option, not a forced first implementation.

---

## 7. Rules, Methods, Declarations

One of the strongest conclusions today:

The system should **not** force a hard split between:

- type declaration
- method
- projection
- computed
- bind

at the root primitive level.

Why:

- in practice they often collapse into the same attached runtime-facing thing
- especially in older Atomic L0 designs
- assembly-like forms often made “field” and “method” indistinguishable in dot notation

So the new clean-room model uses:

```ts
type AtomicRule = {
  id: string
  body: JsonValue
  refs?: AtomicRef[]
}
```

And then the distinction is made by:

- usage
- layer
- projection context
- runtime flavor

not by a hard root enum.

---

## 8. Computed vs Projection vs Bind

Today's clarification here was important.

### Projection

A projection is a view or assembly relative to a chosen axis/scope/checkpoint.

### Computed

If the transform is:

- flat
- non-mutating
- source-preserving

then `computed` can be treated as:

- a cached named projection with identity

That is a clean invariant.

### Bind

If the transform:

- changes source semantics
- changes values materially
- introduces a true operational route

then it should be treated as:

- a new field
- or a bind/real transform

not merely as a computed projection of the same source.

This distinction matters because it keeps:

- lineage clean
- reverse logic simpler
- routing visible

---

## 9. Hashes and Artifacts

Another key refinement:

`hash` should not be a mandatory base field on every object.

Instead:

- hashes are best treated as outputs of projection rules or rulesets
- they are local and projection-relative
- they may be encoded artifacts rather than pretty IDs

### Strong practical stance

One hash mechanism is enough if:

- it is always computed from the relevant projection
- and its context is clear

So instead of forcing:

- structural hash
- runtime hash
- snapshot hash

as separate object fields, it is often better to say:

- `hash = computed from a chosen projection target`

This keeps the model much simpler.

### Locality

Most of these identities are naturally local:

- collection-local
- scope-local
- checkpoint-local

Global universality is usually unnecessary.

### Artifact notion

The user also reminded us of a practical precedent:

- scripts already used compact opaque artifact-like outputs
- then decoded them later

So internal identifiers do not need to be human-readable first.

They should be:

- cheap
- stable enough
- decodable
- usable for cache/routing

This supports the clean-room idea of `AtomicArtifact` as a separate concept from ordinary visible state.

---

## 10. Projection Slots

This is one of the best UI/runtime conclusions from today.

A slot should not first be a place that stores a value.

It should first be:

- a projection point
- a vector
- a transform description
- a rule-attached placeholder

and only later, if successful, become a value holder.

### Stages

1. declared
2. resolving
3. materialized
4. shadow/problem

This is powerful because:

- empty does not mean meaningless
- a not-yet-computed cell is still visible as a slot of computation
- the UI can show how a value will be obtained before it exists

This may become one of the most important interface invariants of the whole project.

---

## 11. Layers

The current Atomic direction is best described as layered.

The four most useful layers fixed in discussion:

### 1. Type Metadata Layer

What types/fragments/aliases/subtypes were encountered.

### 2. Structural Projection Layer

How to compose and display object/list/scope forms.

### 3. Functional Projection Layer

What rule composes or transforms one form into another.

### 4. Transition Virtualization Layer

How to split a transition into dumb atomic instrumental steps.

This is much better than trying to encode all semantics into object primitives.

---

## 12. Structural vs Runtime Projections

This distinction must remain explicit.

### Structural projection

Structural projection answers:

- how the object is shaped
- how it is assembled
- how scopes and hierarchies are organized

### Runtime projection

Runtime projection answers:

- how it is materialized in a particular architecture/runtime flavor
- how relations are resolved operationally
- how reactive or closure-based or assembly-like views behave

These should not be collapsed.

The user explicitly called out multiple runtime flavors:

- React
- closure/lambda style
- assembly-like forms
- signals/websync
- and others

So the abstraction should allow:

- same projection semantics
- different runtime flavors/materializers

without mistaking those differences for separate core object ontologies.

---

## 13. Branching and Shadow Layers

Branching remains a first-class concern, but the preferred model is still:

- branch as projection layer
- branch as shadow object/view
- branch as local semantic divergence

not as giant graph explosion.

Today's discussion reinforced:

- shadow layers can accumulate rule overlays
- structural collapse happens when methods/projections are packed into shadow types and then unify again
- symmetry exists, but not full symmetry
- asymmetry is useful because it can indicate directionality

This supports the broader model from previous sessions:

- branch families
- shadow wrappers
- convergence by compatible projection results

---

## 14. Cursor and Positional Interface

Today's discussion added a strong UI concept:

- use a single canonical cursor-like active point
- `@` is a good compact visual glyph for atomic focus

This can support:

- structural editing
- semantic checkpointing
- progressive flow through projections
- history/optimistic layers

Suggested directional convention from discussion:

- `[-1]` = historical / previous instance side
- `[0]` = current active checkpoint
- `[+1]` = optimistic / next / shadow-resolve side

This is not merely decorative.

It gives a simple consistent mental model for:

- movement
- staging
- replay
- undo/redo
- shadowing

and fits the broader idea of one cursor per agent/user view.

---

## 15. Point, Edge, Rule

A very useful simplification from the discussion:

Instead of thinking in huge object graphs, think in:

- point
- edge
- attached rule

### Point

A checkpointed object/state/scope description.

### Edge

A transform/relation from one point to another.

### Rule

Attached metadata or transform description for the point or edge.

This makes it possible to say:

- object property -> point-attached
- transform/action -> edge-attached

which greatly simplifies both:

- visualization
- artifact hashing

---

## 16. Why Older Comparative Summaries Need Disclaimers

One recurring problem in today's discussion:

summary agents may compare branches or projects too aggressively and conclude:

- “these types look the same”
- “this newer branch supersedes the older one”
- “this old object form collapses to that new wrapper”

This is dangerous because:

- the names may match
- some invariants may match
- but modules and architectural roles may differ

So all future summary/review docs should explicitly state:

1. similarity of names does not imply semantic identity
2. transfer between projects requires comparative schema/dataflow/use-case analysis
3. wrapper-level equivalence does not imply runtime-level equivalence
4. branch recency or documentation clarity does not make a branch architecturally canonical by itself

This disclaimer should be standard in future review-style docs.

---

## 17. Clean-Room Starting Point

The current recommended clean-room start is already written in:

- [ATOMIC_CLEANROOM_BOOTSTRAP_V0_1.md](C:\llm\KoboldCPP agentic sandbox\docs\ATOMIC_CLEANROOM_BOOTSTRAP_V0_1.md:1)
- [atomic_cleanroom_bootstrap.ts](C:\llm\KoboldCPP agentic sandbox\wip\atomic_cleanroom_bootstrap.ts:1)

The clean-room base intentionally keeps only:

- `AtomicObject`
- `AtomicList`
- `AtomicRule`
- `ProjectionSlot`

And a few gestures:

- `putObject`
- `putList`
- `attachRule`
- `declareSlot`
- `materializeSlot`
- `snapshot`

That is enough to start implementation without dragging old code semantics in by accident.

---

## 18. Recommended Next Steps

### 1. Rewrite terminology docs

Especially:

- [ATOMIC_OBJECT_UNIVERSAL_V0_1.md](C:\llm\KoboldCPP agentic sandbox\docs\ATOMIC_OBJECT_UNIVERSAL_V0_1.md:1)

with stronger disclaimers and a more careful distinction between:

- runtime semantics
- wrapper/catalog representation

### 2. Add a formal projection-slot spec

Because this now looks like one of the most important UI/runtime invariants.

### 3. Add a branch/shadow note

Focused on:

- shadow accumulation
- branch convergence
- asymmetry and directionality

### 4. Add a cursor/positional notation note

Based on:

- `@`
- `[-1]`, `[0]`, `[+1]`
- point/edge/rule relation

### 5. Keep the clean-room runtime tiny at first

Do not import old wrappers directly until the vocabulary is fully stabilized.

---

## Final Position

The current Atomic direction is no longer best understood as:

- one universal wrapper over all things

It is better understood as:

- a layered projection/orchestration system
- with dynamic runtime objects
- strong list/scope abstractions
- attached rules rather than prematurely separated method classes
- projection-relative artifacts
- visible computation slots
- explicit structural vs runtime layers
- careful preservation of virtuality vs instancing

That is the most important conclusion from this session.
