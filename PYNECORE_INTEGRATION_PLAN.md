# PyneCore Integration Plan

## Goal

Use `pynecore` as the temporary runtime substrate for the first MVP of the project, instead of building the whole tick/AST/series shell from scratch.

Local source:

- [pynecore](C:\llm\KoboldCPP agentic sandbox\pynecore)

Key reference doc:

- [core-concepts.md](C:\llm\KoboldCPP agentic sandbox\pynecore\docs\overview\core-concepts.md)

## Why Use It

`pynecore` already provides several hard parts we would otherwise need to build:

- import-time AST transformation
- Pine-style repeated tick/bar execution
- `Series` and `Persistent` runtime semantics
- function isolation
- Python-native execution model
- rendering/output-related infrastructure

This makes it a good temporary execution shell.

## Main Architectural Fit

We are **not** adopting PyneCore as-is semantically.

We are using it as:

- a tick executor
- a series/runtime shell
- a potential renderer host
- a convenient Python AST substrate

Our actual project semantics remain:

- hypothesis-centered
- fragment-emitting
- vocab-aware
- matrix/graph/tree projected
- structural-cast-driven rather than rich value-feedback-driven

## Most Important Simplification On Our Side

PyneCore is designed around Pine-like execution where series and persistent state are central.

Our first MVP is simpler in one important way:

- an AST pass does not need to consume freshly produced inner-step values during the same cast
- instead, it keeps applying the same hypothesis/rule form deeper into structure
- the critical product is serialized output fragments for later workers

So we need less of PyneCore's full dataflow semantics than a normal Pine runtime.

## Adopt / Avoid Split

### Adopt Early

Use early:

- AST/import transformation shell
- tick execution substrate
- function isolation
- lightweight series/persistent support where useful
- any rendering/output tools that help visualize matrices/heatmaps

### Avoid Early

Do not depend heavily yet on:

- assignment-heavy Pine semantics
- trading-specific libraries and indicators
- rich built-in financial data assumptions
- complex bar-to-bar value-feedback semantics we do not need

The principle is:

- take the shell
- avoid the domain baggage

## Planned Overlay Layers

We should add our own layer **above** PyneCore rather than modifying all internals immediately.

### Overlay 1: Mediator DSL Layer

This is the pine-like but project-specific orchestration layer.

Responsibilities:

- define frames
- define workers
- define layers and lag
- define tick hooks
- define fragment emission
- define projection targets

### Overlay 2: Fragment Serialization Layer

This is one of the most important project-specific additions.

Responsibilities:

- serialize outputs as small reusable fragments
- attach vocab tokens immediately
- store raw + formal + projection hints
- make fragments easy for later workers to pick up

### Overlay 3: Projection Layer

Responsibilities:

- matrix patches
- graph patches
- semantic tree patches
- heatmap/log outputs

### Overlay 4: Hypothesis/Vocab Layer

Responsibilities:

- map hypotheses to tokens
- store custom vocab forms
- attach bridge representations
- expose fragments for token-based continuation and worker ingestion

## First Integration Strategy

### Step 1

Do not fork `pynecore` logic heavily yet.

Instead:

- keep it vendored locally
- treat it as the execution substrate
- add a thin wrapper package on our side

### Step 2

Build a minimal experiment that:

- runs one tick loop on top of PyneCore
- emits a matrix patch
- serializes one fragment
- logs one path mark

### Step 3

Add lagged worker execution:

- frontrunner worker
- follower worker with `+1` lag

### Step 4

Add vocab-aware output fragments:

- `raw_text`
- `formal_form`
- `vocab_tokens`
- `projection_hints`

### Step 5

Only after the substrate is proven useful:

- start pruning unused Pine/trading pieces
- simplify to project-specific runtime

## Candidate Reuse Areas

Likely useful directories/modules to inspect first:

- [transformers](C:\llm\KoboldCPP agentic sandbox\pynecore\src\pynecore\transformers)
- [core](C:\llm\KoboldCPP agentic sandbox\pynecore\src\pynecore\core)
- [lib](C:\llm\KoboldCPP agentic sandbox\pynecore\src\pynecore\lib)
- [tests](C:\llm\KoboldCPP agentic sandbox\pynecore\tests)

Especially relevant conceptually:

- `SeriesTransformer`
- `PersistentTransformer`
- function isolation behavior

## What We Likely Need To Add Ourselves

PyneCore does not natively give us the project-specific things we care about most:

- hypothesis fragments
- vocab-bound outputs
- semantic tree routing
- coverage matrices
- shortcut/hole summaries
- bridge representation handling

So these should be implemented as explicit overlays, not expected from the base runtime.

## Source Of Truth

Even when using PyneCore, it should **not** become the project source of truth.

Source of truth should remain:

- serialized fragments
- canonical hypothesis identities
- matrix/graph/tree projections
- summary metrics

PyneCore should remain the execution substrate, not the memory model.

## Risks

### 1. Over-adopting Pine semantics

Risk:

- accidentally shaping the project around trading-style dataflow rather than our structural-cast model

Mitigation:

- keep project semantics in wrappers and overlays

### 2. Pulling in too much domain-specific code

Risk:

- wasting effort around finance-specific parts

Mitigation:

- stay focused on transformers/core/runtime shell first

### 3. Refactor debt

Risk:

- temporary convenience becomes permanent architecture

Mitigation:

- clearly mark PyneCore as temporary substrate for MVP

## Short-Term Todo

1. Inspect PyneCore modules most relevant to AST and tick execution.
2. Create a tiny wrapper package for project-specific integration.
3. Define first `OutputFragment` schema.
4. Define first `MatrixPatch` schema.
5. Run one minimal toy tick loop on top of PyneCore.
6. Add one frontrunner and one lagged follower worker.
7. Verify that fragment serialization works without relying on assignment-heavy features.

## Mid-Term Todo

1. Add vocab-bound fragment output.
2. Add matrix/graph/tree sync.
3. Add centered `n-12 .. N .. n+12` cast handling per tick.
4. Add heatmap projection.
5. Add shortcut/hole summaries.
6. Decide which PyneCore pieces to keep permanently and which to replace.
