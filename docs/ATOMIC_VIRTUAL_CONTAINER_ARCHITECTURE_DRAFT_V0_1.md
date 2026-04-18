# Atomic Virtual Container Architecture Draft v0.1

## Purpose

This document fixes the current architectural direction discussed for a new atomic workflow framework.

The goal is **not** to define a linear DSL or a classic runtime graph. The goal is to define a slow, inspectable, coverage-first framework where:

- workflow state is assembled from many small slices
- data can be freely recomposed into virtual objects
- branching is represented as projections over the same data, not as visual graph explosion
- unresolved points become first-class runtime entities
- synthetic coverage can be built before expensive worker execution
- architectural, semantic, and operational invariants can be tracked in parallel with code and data

This framework is intended to support:

- workflow prototyping
- reasoning/debugging over partial systems
- prompt and route exploration
- semantic checkpoint probing
- architecture sanity checks
- agent-facing containerized code editing

It is especially relevant to cases similar to:

- [einstein_case](C:\llm\KoboldCPP agentic sandbox\examples\einstein_case:1)
- [behavior_case](C:\llm\KoboldCPP agentic sandbox\examples\behavior_case:1)
- [quest_order_case](C:\llm\KoboldCPP agentic sandbox\examples\quest_order_case:1)

## Core Thesis

The system should not be modeled as "objects with methods" or as "one canonical workflow".

Instead:

- the substrate is a set of **detached fields**
- virtual objects are cheap **recompositions** over these fields
- methods are better understood as **edges / transforms**
- workflow instances are only **canonical atomic path projections**
- many workflow projections may coexist in parallel
- unresolved state is not an error but a valid runtime condition

The framework therefore acts more like a **lambda batch resolver over virtual containers** than like a classic node/edge execution engine.

## Mental Model

### 1. Open transformations, not fixed objects

The basic semantic unit is closer to:

```txt
lambda[input_state -> output_state]
```

This is only a declaration of checkpoint tension, not a full execution step.

To become operational, a declarative checkpoint relation is paired with a local resolver:

```txt
messages -> messages[reactions[:thumbsupp:]]
:: each message add reaction(:thumbsupp:)
```

Important:

- the declaration of the target does not imply that the target is fully resolved
- the resolver may close only part of the gap
- unresolved residue is expected and must be materialized

So the real runtime atom is:

- source checkpoint
- resolver slice
- target checkpoint
- residue: unresolved fields, invariants, branch candidates, anomaly tags

### 2. Workflow is not a singleton

There is no single "main workflow" invariant.

Instead:

- a workflow instance is one **canonical atomic path projection**
- many workflow projections may be materialized at once
- they may diverge, merge, or remain parallel
- automatic branches may create new workflow projections

This makes workflow a **materialized view over rule space**, not the primary object of the system.

### 3. Branches are semantic partitions, not graph explosion

If a branch depends on input data, the cause of the branch already exists in the input.

Therefore branching should be represented as:

- semantic tags on input containers
- alternative projections over the same container set
- optional problem containers for ambiguous or failing cases

Instead of:

- a giant visual branch tree

we want:

- one container space
- multiple semantic overlays
- multiple projection dimensions

This makes large invariant systems much easier to debug and inspect.

## Main Entities

### Detached Fields

Detached fields are the lowest-level substrate.

They are good for:

- atomic storage
- dependency tracking
- projection input sets
- constraint evaluation

They are intentionally not sufficient as direct execution surfaces.

### Virtual Containers

A virtual container is a recomposed object view built from detached fields.

A container is:

- cheap to materialize
- free to reshape
- suitable as a carrier for transforms
- disposable if a projection no longer matches

This is a strength, not a weakness:

- one data substrate may be viewed as many virtual objects
- methods can fire whenever required field sets are present
- no named object schema is required as the primary truth

### Projections

A projection is a view or derived composition over one or more containers.

Projection dimensions may include:

- semantic interpretation
- response shape
- architecture
- serialization
- debug
- trace
- evaluation
- branch classification

Different projection families should be kept distinct so that, for example:

- hypothesis branches
- response variants
- architecture interpretations

do not pollute the same view.

### Shadow Projections

Shadow projections exist to carry:

- partial matches
- comparable but non-identical objects
- synthetic representations
- structural warnings
- research-only alternatives
- architecture overlays

If a working object is close to a reference object but not identical, the match should not fail globally. It should move into a shadow projection.

### Problem Objects

Whenever the runtime encounters a mismatch, ambiguity, or failure, it should be able to materialize a problem object rather than only producing a raw error.

Examples:

- split boundary unclear
- missing fields for transform
- unexpected return shape
- constraint violation
- reverse mapping mismatch

These objects can then drive:

- retries
- patches
- synthetic examples
- prompt experiments
- worker exploration

## Identity and Grouping

### Virtual type is structural, not nominal

Containers are not primarily named by a static declared type.

They are grouped by structural compatibility:

- field sets
- template membership
- schema membership
- tag mapping
- normalized shadow mapping

One practical mechanism is a **union hash** derived from the current structural shape.

If two containers converge to the same normalized template/schema/hash:

- they can collapse into one container family

If they diverge:

- they split into different container groups

This is a valid runtime situation, not a failure.

## Resolve Cycle

## High-level view

The runtime is not a simple left-to-right traversal.

It behaves more like:

- local casting
- forward propagation
- backward propagation
- per-node saturation
- anomaly marking
- regrouping
- container merging/splitting

The best short description is:

**bidirectional saturating resolve over virtual containers**

### Perpendicular saturation

The main dynamic is not only "left to right" and "right to left".

Rather:

- on every node, neighboring transforms at distance 1 are cast against available container compositions
- resulting fields and branches are compared
- anomalies are marked
- new containers are created if needed
- invariant information is propagated backward
- newly stabilized fields are propagated forward

This repeats until local fixpoint.

### Why this matters

This allows:

- complete structural exploration before expensive generation
- branch growth and branch collapse
- discovery of missing resolvers
- synthetic test generation as a by-product
- localization of failures at checkpoints instead of end-of-pipeline failure

## Split / Merge Behavior

At a high level:

- right-side unresolved variants create more container multiplicity
- left-side stabilized fields create more shared compatibility

So branch count and container count both evolve, but:

- branches do not only grow
- they can collapse once normalized again

The runtime rhythm is:

- split
- carry
- compare
- resolve
- merge

## Synthetic-First Strategy

The generator is expensive and unstable. Therefore the engine should do everything possible before asking a model.

### Goal

Minimize generator work by:

- precomputing structural transitions
- saturating projections
- generating synthetic representatives
- classifying branch and anomaly types
- prebinding candidate prompts/tasks to unresolved points

Then, when a worker is finally called, its answer should already be constrained by:

- expected container classes
- expected output shapes
- known anomaly classes
- known branch surfaces

In the ideal case:

- the answer is validated immediately
- the point of failure is obvious
- the next route is obvious

### Synthetic value representation

Every marked property or field should be able to carry not only:

- semantic tags
- structural metadata

but also a **synthetic representative value**.

This supports:

- forward saturation
- reverse checks
- undo/redo checks
- schema and template validation
- synthetic branch coverage

### Structural first, semantics later

The framework should first attempt:

- structural branching
- branch-space enumeration
- constraints and field compatibility

and only then use workers for unresolved semantic decisions.

This is especially useful for prompt and route exploration.

## Fixtures and Coverage

Fixtures should not only capture final outputs. They should also capture expected resolution behavior.

Fixtures may contain:

- starting containers
- expected projections
- expected unresolved sets
- expected conflicts
- expected chosen branches
- candidate rule variants

This allows testing:

- not only what was returned
- but how the system converged

## Background Exploration

One of the strongest implications of this architecture is that unresolved points can automatically produce research tasks.

If worker capacity is free, the system can:

- detect unresolved points
- detect branch ambiguity
- detect strange return families
- spawn local synthetic or worker-backed exploration

without blocking the main workflow.

This enables:

- prompt experiment mining
- output normalization mining
- return-shape family discovery
- boundary-case generation

The key is that these experiments operate on local problem containers, not on the entire workflow.

## Architecture Projection

The system should maintain a semantic architectural projection parallel to the implementation.

This does not need to be a perfect automatic architecture model.

It is already useful if it serves as:

- a sanity-check layer before implementation
- a drift detector during implementation
- a lightweight architectural memory bound to the same containers as the code

Why this matters:

- architecture notes in markdown drift away from code
- chat discussions contain local reasons that are lost later
- LLMs handle small architecture edits easily but lose the architectural overview under generic code mass

So architecture should be stored as:

- projections over code containers
- local rationale tags
- tradeoff notes
- agreement checks

not only as detached prose files.

## Code and Agent IDE Implications

The same model can act as a strong MCP-IDE substrate for agents.

### Why

The hardest practical part for agents in large codebases is:

- selecting the right code slice
- applying safe patches
- surviving offset drift and line movement
- noticing structural breakage early

If code is containerized by AST/block/semantic scope:

- LLMs can address code by stable container identity
- text movement stops being the primary coordinate system
- local patches can remain human-discussable
- structural breakage can be surfaced as projection mismatches

### Git interaction

Git should remain the human-facing linear source of committed projected code.

But the richer structure should live in parallel as shadow data:

- container mapping
- tags
- structural projections
- architecture projections
- agent-facing metadata

A practical rule:

- Git stores projected state
- shadow storage stores semantic/container structure

## Runtime Agreement Monitoring

The system should also support real-time subscriptions on invariants and agreements.

Examples:

- one user action should cause one `exec()`
- a boundary must not be crossed
- an entrypoint must not produce multiple side-effect chains

These checks can be implemented as:

- a tiny smoke rule file
- a projection onto a selected entrypoint
- bindings to agreed invariants

This is enough to turn many informal team agreements into live runtime sanity checks.

## Controlled Natural Language

Because the system uses:

- allowed scope names
- allowed projection names
- container families
- constrained operation forms

it should be realistic to support a semi-formal natural language layer that compiles into DSL slices.

This does not require full unrestricted NLP.

It only requires controlled language over:

- named scopes
- known fields
- known projection families
- known transitions

This opens the door to:

- NL authoring
- DSL lowering
- reverse serialization back to readable explanations

## Non-Goals

This architecture is not trying to:

- replace Git
- replace code with a universal DSL
- solve semantic routing perfectly
- fully automate architecture design
- eliminate generators entirely

It is trying to:

- reduce manual bottlenecks around model use
- reduce prompt and route debugging pain
- keep architecture and implementation tied together
- make unresolved state inspectable
- make branching and coverage manageable
- let the generator work only on what truly needs generation

## Practical Design Rules

1. Keep detached fields as substrate, not as the human execution surface.
2. Materialize virtual containers freely and cheaply.
3. Treat methods as transforms over required field sets.
4. Keep branching in projections/tags rather than exploding the visible graph.
5. Saturate structurally before spending model calls.
6. Store architectural knowledge as projections, not only prose.
7. Keep synthetic and live worker data in the same resolution framework.
8. Treat exceptions as typed problem objects when possible.
9. Use workflow projections as materialized views, not as singleton truth.
10. Keep Git as projected state and shadow structure as sidecar truth.

## Summary

The proposed framework is best understood as:

- an atomic coverage-first reasoning substrate
- based on detached fields, virtual containers, and projections
- using bidirectional/perpendicular saturation rather than only linear execution
- with many workflow projections, not one workflow singleton
- where unresolved state is a first-class runtime object
- where architecture, debug, code, prompts, and semantics all live as parallel projections over the same underlying structure

This makes it suitable not only for workflow execution, but also for:

- reasoning support
- prompt and route exploration
- agent IDE operations
- architecture sanity tracking
- checkpoint-centered debugging
- synthetic coverage generation

The framework should remain intentionally rough and slow if needed. Speed is secondary. Coverage, inspectability, and reusable structure are the main goals.
