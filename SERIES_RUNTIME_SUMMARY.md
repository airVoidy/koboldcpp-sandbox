# Series Runtime Summary

## Goal

Capture the agreed runtime model for hypotheses as reactive, layered, series-like programs rather than static graph nodes.

This document focuses specifically on:

- hypothesis-as-series behavior
- layered expansion
- depth-bounded unfolding
- tick-based reactive recomputation
- matrix patch emission

## Core Idea

A hypothesis should not be treated as just a stored statement.

A hypothesis behaves more like a reactive functional object:

- it has semantic content
- it has dependencies
- it reacts to rule changes
- it emits effects into system state
- it can be replayed from depth `0`

So a hypothesis is closer to a small reactive program than to a passive record.

## Pine Script Analogy

The comparison with Pine Script is intentional and useful.

In Pine Script, a script behaves like a series evolving over bars/ticks.

In this framework, a hypothesis behaves like a series too, but not as a simple scalar time series.

Instead:

- a hypothesis produces structured state
- output is not just one value
- output can update a 2D matrix or other projections

So a hypothesis is more like:

- a reactive state series
- a patch emitter
- a layered local simulation

## Hypothesis as Series

Working model:

- each hypothesis is a `HypothesisSeries`
- on each evaluation pass, it emits a state contribution
- the contribution may affect:
  - matrix cells
  - graph links
  - semantic tree nodes
  - derived facts
  - conflict markers

Conceptually:

```text
HypothesisSeries(tick) -> MatrixPatch + GraphPatch + TreePatch + DerivedFacts
```

The output is not necessarily a single boolean.

It may be:

- `true`
- `false`
- `unknown`
- narrowed domain
- derived assignment
- branch-local conflict
- unresolved hole

## Reactive Functional Node

A graph node is better modeled as a reactive functional object.

Suggested conceptual fields:

- `id`
- `expr`
- `inputs`
- `outputs`
- `state`
- `rules`
- `dependencies`
- `subscribers`
- `branch_scope`

This means:

- rules can be attached to the node
- changing a rule invalidates dependent nodes
- recomputation happens in the same scheduler pass / tick
- no unnecessary object duplication is required

This is intended as functional/reactive runtime semantics, not a JavaScript/React reference model.

## Triple Meaning vs Runtime Behavior

The semantic triple still exists:

- `subject`
- `relation`
- `object`

But it is only the semantic signature of the hypothesis.

The runtime behavior is separate:

- how it updates state
- what projections it changes
- what downstream nodes it invalidates
- what new facts it derives

So:

- triple = meaning
- series = runtime behavior
- patch = concrete effect on system state

## Matrix Patch Model

Each hypothesis can emit a `MatrixPatch`.

A patch may contain:

- changed cells
- narrowed candidate domains
- added exclusions
- added assignments
- confidence / status changes
- local conflicts

Example conceptual shape:

```text
MatrixPatch = {
  cells_changed,
  constraints_added,
  conflicts_found,
  notes,
}
```

This makes a hypothesis behave like a local 2D state transformer.

## Not 1D but 2D

Unlike ordinary charting series, the state here is not just one-dimensional.

Each hypothesis can be thought of as producing a structured 2D surface or matrix contribution:

- rows and columns may represent entities, slots, roles, or candidates
- each tick updates some subset of those cells

So:

- ordinary Pine-like series: `time -> scalar`
- our runtime: `tick -> matrix slice / patch`

## Nested Series

We agreed that there may be multiple levels of series nesting.

This is important.

The runtime is not only:

- tick series

It may also contain:

- depth series
- layer series

## Depth Series

For a given hypothesis or local subgraph:

- depth `0` is the current tick center
- backward exploration goes toward `-12`
- forward exploration goes toward `+12`
- each tick therefore sees a local centered cast window

Current intended bound:

- `-12 .. +12`

So one tick effectively contains a partial local horizon of depth up to `24`, centered at `N`.

In this discussion, depth `12` is not just a random heuristic. It is related to the topology/structure basis coming from project `314`.

So a local series can be modeled as:

```text
DepthWindow(N) -> casts over [-12..+12] -> local patches / intersections / consequences
```

## Layer Series

There is also an outer series.

Important correction:

- layer progression is not the same thing as depth progression
- `wave 1` and `wave 12` are not different execution kinds
- each tick already performs the same centered cast logic

Layers exist above that repeated tick logic.

So:

1. the mediator advances one tick
2. each tick performs the same `n-12 .. n .. n+12` style cast pattern
3. resulting overlaps, shortcuts, holes, and patches are merged
4. higher layers can then change rules, context, or projection state

This means the runtime works layer-by-layer above a stable per-tick execution rule.

Examples of layers:

- initial answer frame
- first hypothesis wave
- meta-analysis layer
- historical-linking layer
- branch-disambiguation layer

So the runtime grows by stacking layers after a series endpoint is reached.

## Tick / Depth / Layer Axes

The runtime is best understood with three axes:

- `tick`
- `depth`
- `layer`

### Tick

One reactive recomputation pass.

Every tick performs the same structural operation:

- backward cast
- current fixation
- forward cast

The behavior differs because hypothesis atoms and their states differ, not because the scheduler changes its core action.

### Depth

Local unfolding distance from a seed hypothesis.

### Layer

Outer orchestration stage added after a previous series reaches an endpoint.

This is more precise than a simple linear stream.

## Suggested Model

Conceptually:

```text
Layer
  -> changes context / rules / overlays
       -> TickPass
            -> performs centered DepthWindow cast
                 -> emits patches
```

Or:

```text
layer -> tick -> depth-window -> patch
```

This is the intended mental model for runtime design.

## Saturation

A local series is considered saturated when at least one of these holds:

- no new derived facts appear
- no matrix cells change
- only repeated substructures are generated
- a contradiction closes the branch
- a branch fork requires explicit alternate exploration
- configured depth limit is reached

After saturation, the runtime should not blindly continue the same series.

Instead it should:

- summarize
- analyze holes/shortcuts/conflicts
- decide whether to add another layer

## Replay

Because hypotheses are series-like and reactive, the system should support replay.

Replay means:

- return to depth `0`
- apply new rule packs or extra context
- re-run affected hypotheses
- recompute dependent projections

This is a key advantage of the reactive model.

It allows:

- rule replacement
- branch comparison
- debugging
- historical re-evaluation
- incremental refinement

## Rule Packs

A hypothesis should be attachable to sets of rules.

A `RulePack` can define:

- local derivation logic
- compatibility checks
- patch merge rules
- invalidation rules
- projection updates

Changing a `RulePack` should trigger reactive recalculation in the same scheduling cycle or next deterministic tick.

## Projection Behavior

A hypothesis series should update multiple views in sync:

- matrix view
- causal graph view
- semantic tree view

This suggests a shared patch model:

- `MatrixPatch`
- `GraphPatch`
- `TreePatch`

with one scheduler applying them consistently.

## Push / Pop / Skip

In the semantic tree layer, we discussed navigation semantics:

- `push`
- `pop`
- `skip`

These map well onto layered series traversal:

- `push`: descend into derived/local consequence structure
- `pop`: return to prior semantic frame
- `skip`: move to sibling / alternate / neighbor path

This is useful both for navigation and for local runtime scheduling.

## Practical Runtime Interpretation

The intended runtime is therefore not just:

- a graph database
- a batch solver
- a static rule engine

It is closer to:

- a reactive functional runtime
- a layered replay engine
- a patch-based matrix/graph synchronizer

## Working Vocabulary

Useful terms agreed or implied during discussion:

- `HypothesisSeries`
- `LayerSeries`
- `DepthSeries`
- `TickPass`
- `MatrixPatch`
- `GraphPatch`
- `TreePatch`
- `RulePack`
- `Replay`
- `Saturation`
- `DepthWindow`
- `CenteredCast`

## Connection to Project 314

Project `314` is relevant here because it suggests a mathematically grounded structural basis for ternary semantic systems.

This matters for the series runtime because:

- depth `12` can be treated as a meaningful topological expansion bound
- semantic tree expansion can be constrained by structural classes
- runtime transitions can be validated against known structural rules

So the future runtime should likely use `314` as a structural/topological foundation for semantic-tree behavior.

## Per-Tick Semantics

Another important clarification:

- every tick does the same thing
- what changes is the internal logic of hypothesis atoms and their date/state-dependent behavior

This is one of the reasons Pine Script is a good execution reference.

The analogy is not about syntax only, but about runtime semantics:

- the scheduler repeatedly executes the same tick model
- atom behavior changes depending on current state/history/date
- outputs are recomputed as reactive series

So the runtime should be designed more like:

- fixed tick semantics
- variable atom logic
- deterministic projection updates

than like a sequence of fundamentally different execution phases.

## Implementation Direction

For a small MVP, the layered series model can be implemented in this order:

1. Define a minimal `HypothesisSeries` abstraction.
2. Define `MatrixPatch`.
3. Add a basic `TickPass` scheduler.
4. Add `DepthSeries` expansion with a small limit.
5. Add saturation detection.
6. Add replay from depth `0`.
7. Add `LayerSeries` orchestration.
8. Synchronize matrix/graph/tree projections.

This should be tested first on very small ordering/constraint cases before adding richer semantic structures.
