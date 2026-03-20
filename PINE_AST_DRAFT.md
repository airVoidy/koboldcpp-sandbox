# Pine-Like AST Draft

## Purpose

Define a first draft of the pine-style mediator layer for the project.

This layer is not the full semantic runtime.

It is the top orchestration and logging layer that:

- runs in ticks
- coordinates heterogeneous worker modules
- records heatmap/table state
- marks paths discovered by frontrunner agentic passes
- lets slower follow-up layers replay and analyze the same data with a `+1` lag

## Core Runtime Picture

The system contains multiple modules with very different logic.

The thing they share is:

- all of them are tick-based
- all of them can be projected into the same mediator timeline
- all of them can emit patches into shared 2D/graph/tree views

So the mediator behaves like a Pine-style runtime:

- every tick executes the same top-level scheduler contract
- different modules run their own internal logic
- modules may run with different speeds and lags
- results are merged into synchronized projections

## Main Execution Idea

At tick `N`:

1. Frontrunner agentic modules do a fast pass and mark candidate paths.
2. Those path marks are stored in mediator state.
3. Deeper/slower layers run behind that frontrunner with lagged replay.
4. Each lagged layer performs the same stepwise analysis over the same data.
5. All layers emit patches into the same logging/projection system.

So the system is:

- parallel in execution
- synchronized by tick
- layered by lag

## Pine Analogy

The Pine-style comparison is mainly about execution semantics:

- one repeated tick protocol
- state carried across ticks
- declarative top-level expressions
- replayability
- stepwise logging
- deterministic projection updates

This layer is not meant to copy TradingView.

It is meant to copy the useful idea:

- stable tick-driven execution over stateful series

## Main Difference From Pine Script

The most important simplification on our side:

- an AST pass to the maximum depth does **not** use newly produced data as input for the next inner step of the same run
- instead, it keeps applying the same hypothesis/rule structure farther and farther over the allowed topology

So unlike Pine-style dataflow where later bars/ticks may directly consume updated series values during the ongoing execution model, our pass is closer to:

- structural propagation of the same hypothesis
- over deeper reachable regions
- with output collected externally

This makes the runtime simpler in one very important way:

- we do not need arbitrary "read next tick data during the current run" semantics

## Consequence of This Simplification

Because inner propagation is structure-driven rather than data-driven, the AST core can stay more generic.

What becomes critically important instead is output handling.

Every step must:

- generate output fragments
- fragment them into reusable serialized pieces
- attach vocab-aware forms immediately
- make them easy to parse, reattach, and consume by later workers

So the central problem is less:

- "how do we feed newly produced runtime values back into the next inner step?"

and more:

- "how do we emit structured fragments that future workers can pick up automatically?"

## First AST Requirement

The AST for the mediator must represent:

- declarations
- stateful series
- layers
- worker bindings
- patches
- routing marks
- lagged replay links
- projection updates

## Proposed AST Families

### 1. Program Nodes

- `Program`
- `Import`
- `ConfigBlock`
- `DictionaryRef`
- `RulePackRef`

### 2. Frame and Projection Nodes

- `FrameDecl`
- `MatrixDecl`
- `HeatmapDecl`
- `GraphDecl`
- `TreeDecl`
- `ProjectionDecl`

These describe what shared output spaces exist.

### 3. Series and State Nodes

- `SeriesDecl`
- `StateDecl`
- `VarDecl`
- `BufferDecl`
- `WindowDecl`
- `LagDecl`

These represent tick-carried state.

### 4. Worker Nodes

- `WorkerDecl`
- `WorkerGroup`
- `WorkerBind`
- `WorkerSchedule`
- `WorkerPatch`

These represent heterogeneous compute modules.

### 5. Tick Execution Nodes

- `OnTick`
- `Step`
- `Emit`
- `Merge`
- `Replay`
- `Commit`

These define what the mediator does each tick.

### 6. Path and Route Nodes

- `PathMark`
- `PathScore`
- `PathMask`
- `ShortcutMark`
- `HoleMark`
- `RouteBind`

These represent frontrunner-discovered paths and later re-analysis.

### 7. Layer Nodes

- `LayerDecl`
- `LayerInput`
- `LayerOutput`
- `LayerLag`
- `LayerReplay`
- `LayerMerge`

These represent stacked analysis passes.

## Minimal Execution Semantics

Every tick uses the same high-level contract:

1. Read current shared state.
2. Run bound workers that are active for this tick.
3. Collect path markings from frontrunners.
4. Replay lagged layers over already marked paths.
5. Merge all patches.
6. Update projections.
7. Append to tick log.

Important:

- the scheduler contract stays the same
- behavior differs because workers, state, lag, and rules differ

## Frontrunner / Follower Model

The intended pattern is:

- `frontrunner` modules run first and fast
- they mark available or promising paths
- `follower` layers trail them with `+1` lag or more
- followers perform deeper stepwise analysis over the marked data

So frontrunners do not solve the whole task.

They provide:

- path seeds
- route candidates
- coverage hints
- branch markers

And lagged layers do:

- slower validation
- refinement
- decomposition
- semantic replay

## Lag Semantics

Lag is a first-class AST concept.

Examples:

- `lag = 0`: runs on current tick
- `lag = +1`: runs one tick behind frontrunner output
- `lag = +k`: runs `k` steps behind current frontier

This lets all layers stay inside the same tick framework while still being staggered.

## AST Node Sketch

### Program

```txt
Program(
  imports=[],
  configs=[],
  frames=[],
  matrices=[],
  series=[],
  workers=[],
  layers=[],
  on_tick=[]
)
```

### SeriesDecl

```txt
SeriesDecl(
  name,
  kind,
  initial,
  window=None,
  lag=0
)
```

### WorkerDecl

```txt
WorkerDecl(
  name,
  worker_type,
  input_refs=[],
  output_refs=[],
  lag=0,
  enabled=True
)
```

### LayerDecl

```txt
LayerDecl(
  name,
  source_workers=[],
  input_projections=[],
  output_projections=[],
  lag=1,
  merge_policy="default"
)
```

### OnTick

```txt
OnTick(
  steps=[
    Step(...),
    Step(...),
    Merge(...),
    Emit(...),
    Commit(...)
  ]
)
```

## DSL-Like Example

This is not final syntax, only a semantic sketch.

```txt
frame order_frame
matrix coverage_map size 12x12
heatmap path_heat size 12x12

series frontier_marks lag 0
series lagged_analysis lag 1

worker fast_paths type frontrunner lag 0
worker semantic_replay type follower lag 1
worker hole_scan type follower lag 2

layer L0 uses fast_paths -> frontier_marks
layer L1 uses semantic_replay -> coverage_map
layer L2 uses hole_scan -> path_heat

on_tick:
  run fast_paths
  mark frontier_marks
  replay semantic_replay from frontier_marks
  replay hole_scan from coverage_map
  merge coverage_map, path_heat
  emit tick_log
```

## Required Patch Types

Workers should emit patches rather than full states.

At minimum:

- `MatrixPatch`
- `HeatmapPatch`
- `GraphPatch`
- `TreePatch`
- `PathPatch`
- `LogPatch`

This keeps the mediator lightweight and replay-friendly.

## Output Fragment Requirement

Output should be fragmented deliberately.

Each step should emit units that are:

- serializable
- vocab-aware
- easy to parse mechanically
- easy to rebind to later worker passes
- easy to project into matrix / graph / tree layers

These fragments should be treated as first-class runtime products.

Suggested conceptual output fragment fields:

- `fragment_id`
- `source_tick`
- `source_layer`
- `source_worker`
- `hypothesis_ref`
- `vocab_tokens`
- `raw_text` (optional)
- `formal_form`
- `projection_hints`
- `coverage_delta`
- `route_marks`

This allows later workers to consume outputs without re-running the whole semantic interpretation layer.

## Logging Model

The mediator must log by tick.

At minimum each tick log should capture:

- active workers
- active layers
- path marks created
- lagged replays run
- projection patches emitted
- merge summaries
- holes / shortcuts / conflicts detected

This logging is one of the reasons the Pine-style layer is useful.

## Relationship to Semantic Trees

The mediator does not replace semantic trees.

Instead:

- semantic trees provide route structure
- workers operate over semantic/tree/graph/matrix data
- the mediator synchronizes their stepwise outputs

So this AST is orchestration-first, not semantics-first.

## Relationship to n-1 / N / n+1

The mediator should be able to represent centered cast semantics too.

At tick `N`, a worker may internally do:

- `n-1` verification
- `N` fixation
- `n+1` fanout

But from the mediator point of view, this is still just:

- one worker step
- one emitted patch bundle

This keeps the orchestration layer simple.

## AST Scope Clarification

The AST should stay mostly framework-agnostic.

It should support:

- general declarations
- calls
- functions
- blocks
- tick hooks
- emission points
- object bindings

Framework-specific meaning should come from builtins and runtime bindings, not from hardcoding all mediator semantics into AST node types.

This matches the simplification above:

- AST describes how passes are structured
- runtime builtins define what gets emitted, projected, and rebound

## MVP Scope

The first MVP AST should only support:

- one frame
- one or two matrices
- a few series
- two worker classes:
  - frontrunner
  - follower
- lag
- patch merge
- tick logging

No need to implement the full semantic runtime at this layer yet.

## Todo

1. Define exact AST dataclasses for the nodes above.
2. Define minimal textual DSL syntax for `frame`, `series`, `worker`, `layer`, `on_tick`.
3. Define patch schemas for matrix/heatmap/path/log.
4. Define merge policy contract.
5. Define lag semantics precisely.
6. Define how frontrunner path marks are stored and exposed to followers.
7. Build one toy example with:
   - one frontrunner
   - one lagged follower
   - one 12x12 heatmap
   - one tick log
