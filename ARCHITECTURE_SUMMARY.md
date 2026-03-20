# Architecture Summary

## Goal

Build a local agentic sandbox over `koboldcpp` where a reasoning model generates hypotheses, framework workers formalize and check them, and the system accumulates verified structure across multiple synchronized representations.

The target is not a single linear chain-of-thought store, but a reusable framework for:

- parsing task questions into answer schemas
- atomizing conditions into typed hypotheses
- expanding consequences to bounded depth
- tracking causal and semantic links between claims
- checking branch compatibility and intersections
- compiling verified facts into a fast execution layer

## Core Principle

`git` branches are runtime sandboxes for hypothesis execution, not the primary knowledge model.

Knowledge should live in a canonical fact/hypothesis layer, with multiple projections built on top of it:

- tabular answer/result view
- causal graph
- ternary semantic tree

## Top-Level Pipeline

1. Analyze the question and infer the answer form.
2. Build a draft answer frame from the question only.
3. Parse the condition text into raw claims.
4. Atomize raw claims into typed hypothesis units.
5. Formalize those atoms into normalized constraints/triples.
6. Project them onto the answer frame.
7. Expand consequences up to bounded depth.
8. Run semantic/meta analysis on the resulting structure.
9. Highlight shortcuts, holes, cycles, conflicts, and next-best checks.
10. Compile verified facts into a fast runtime layer.

## Answer-First Framing

We decided that the first step is not "build a hypothesis graph", but "understand what the answer must look like".

For example, in the puzzle:

> Determine the order in which participants entered the room and who left the note.

The answer form is:

- an ordered assignment
- plus an extra distinguished entity (`author`)

Important: the shape of the answer comes first, while the exact size or concrete filled values may be derived later.

This matters because some tasks may require:

- finite order
- parametric order
- infinite order with computable pattern

So the framework should first create a draft `AnswerFrame`, then let condition-derived hypotheses refine it.

## Stage Model

### Stage 0: Question Analysis

Extract:

- target answer type
- output structure
- axes and roles
- whether size/cardinality is known, derived, or parametric

### Stage 1: Draft Answer Frame

Create a skeletal answer layout, for example:

- ordered assignment
- unknown length `N`
- entity axis
- optional distinguished role slots like `author`

At this point the frame is only a draft, not yet verified by constraints.

### Stage 2: Raw Claim Extraction

Parse the task condition into raw statements, preserving wording and provenance.

Example raw claim:

- `Каждый участник заходил в комнату с ящиком ровно один раз и поодиночке.`

### Stage 3: Atomization

Split raw claims into atomic units suitable for checking and propagation.

A raw statement may produce several formal atoms.

For example, the single raw claim above may unfold into:

- each listed person enters exactly once
- entries are non-overlapping / one at a time
- the answer structure supports a total order of entry events

### Stage 4: Formalization

Convert atoms into normalized forms.

We converged on a triple-like core representation:

- `subject`
- `relation`
- `object`

Examples:

- `(Илья, after, Диана)`
- `(Лера, immediately_after, Софья)`
- `(author, before, Максим)`

### Stage 5: Projection

Project formalized atoms into multiple synchronized views:

- answer/result tables
- causal graph
- semantic tree

### Stage 6: Bounded Expansion

Expand consequences through a centered local cast window.

Current working rule:

- each tick is centered at `N`
- local casts explore backward to `N-12`
- local casts explore forward to `N+12`
- effective local horizon is therefore up to `24`

After local saturation and merge, run semantic analysis over the resulting structure.

### Stage 7: Meta Analysis

Framework-level analysis should identify:

- shortcuts
- holes
- cycles
- contradiction clusters
- weak branches
- high-value next checks

## Hypothesis Model

We aligned on a distinction between several levels:

- `entity`: objects mentioned in the problem, like people
- `raw claim`: natural-language statement extracted from the prompt or thought
- `hypothesis atom`: smallest meaningful reasoning unit for checking
- `formal constraint`: normalized machine-usable representation
- `derived fact`: verified consequence produced by framework logic
- `branch hypothesis`: explicit alternative path explored in a sandbox branch

Important:

- people themselves are not hypotheses
- statements about them are hypotheses

Example:

- `Елисей` is an entity
- `Елисей первый` is a hypothesis
- `Елисей последний` is another hypothesis

## Structural vs Relational Hypotheses

We separated hypotheses into at least two major kinds:

- `structural`
- `relational`

Structural hypotheses create or justify the problem frame itself.

Example:

- "Each participant enters exactly once and individually"

Relational hypotheses constrain values inside an already established frame.

Examples:

- `Илья после Дианы`
- `Лера сразу после Софьи`
- `Елисей либо первый, либо последний`

This distinction matters because some checks depend on the frame existing first.

## Two Ternary Layers

We converged on two different ternary-style layers.

### 1. Claim Triple Layer

Semantic content of the claim:

- `subject`
- `relation`
- `object`

### 2. Meta-Semantic Link Layer

How one node is related to another in the reasoning structure:

- parent / child
- same-level neighbor
- other linked node

Operationally this can later be refined into:

- `derived_from`
- `depends_on`
- `supports`
- `contradicts`
- `same_level_related`
- `shortcut_to`
- `fills_hole_for`

The key distinction:

- triple layer answers: "what is being claimed?"
- link layer answers: "how does this claim relate to other claims?"

## Required Coexisting Representations

We agreed the framework should keep the same knowledge in multiple synchronized forms.

### 1. Table View

Used for:

- answer state
- intermediate state
- candidate slots
- verified and branch-local cell values
- per-cell supporting hypotheses

### 2. Causal/Reasoning Graph

Used for:

- cause -> consequence
- support and contradiction
- dependency tracking
- shortcut discovery
- hole detection

### 3. Ternary Semantic Tree

Used for:

- normalized semantic structure
- local reasoning traversal
- push / pop / skip navigation

Navigation semantics discussed:

- `push`: descend into a consequence or nested local structure
- `pop`: return to prior semantic context
- `skip`: move to sibling / neighbor / alternative local node

## Canonical Storage + Projections

We do not want three unrelated stores. The same fact should have one canonical identity and several projections.

Canonical layer should own:

- fact identity
- provenance
- depth
- verification status
- branch scope

Projection layers should only reference canonical facts.

Recommended conceptual split:

- canonical fact store
- matrix projection
- causal graph projection
- semantic tree projection

## Depth-12 Expansion Rule

Current intended strategy:

- extract seed atoms
- for each active tick, cast over the centered window `[-12..+12]`
- merge overlaps, shortcuts, holes, and conflicts
- after local saturation, analyze graph semantics globally

Expected outputs of post-depth analysis:

- `shortcuts`: short strong derivations that collapse many alternatives
- `holes`: explicit missing information or unresolved branch discriminators
- `cycles`: dependency loops or semantic repetition
- `conflict_clusters`: inconsistent local regions

## Dictionary-Driven Framework Layer

A major design decision is to standardize the upper utility layer around dictionaries and mappings, inspired by project `314`.

External dictionaries should define semantic primitives and tokens.

Per-case mapping should define how those tokens become:

- entities
- formal atoms
- constraints
- branch hypotheses
- answer-frame projections

So the framework becomes a generalized mapper from:

- dictionary space
- task-specific answer frame

into:

- runtime hypotheses
- graph links
- checks
- projections

## Reuse From Project 314

We identified useful transferable concepts from `C:\llm\314`:

- token dictionaries as external hypothesis layouts
- fit-based branch selection and commit
- accepted vs rejected branch accounting
- hole logging
- evaluation by coverage and branch efficiency, not only top-1 correctness

This suggests the future puzzle/runtime framework can reuse ideas like:

- typed hypothesis dictionaries
- branch scoring
- accepted/rejected check logs
- coverage/selectivity-style metrics
- hole extraction for planning next checks

## Planned Standardized Specs

We expect to standardize at least these top-level formats:

- dictionary schema
- answer frame schema
- mapping schema
- runtime check contract

Likely runtime contract phases:

- extract
- classify
- map
- propagate
- branch
- check
- commit
- log holes

## Example Interpretation of the Puzzle

At the very earliest stage we only definitely know:

- the listed participants as entities

We do not immediately treat the final order length as already verified world structure. Instead:

- the question implies an order-shaped answer
- the condition contributes structural hypotheses
- those structural hypotheses justify materializing the order frame

So:

- `persons = [Лера, Максим, Софья, Илья, Диана, Елисей, Анна]`
- answer frame draft says: "some order over entities is required"
- structural claims later justify stronger facts like one-time entry and slot assignment

## Implementation Direction

Implementation should proceed with small layered cases.

Recommended order:

1. Question-to-answer-frame parser.
2. Raw claim extractor.
3. Atomizer for simple ordering problems.
4. Triple representation and canonical fact store.
5. Table projection for ordered-assignment tasks.
6. Causal graph projection.
7. Semantic tree projection with push/pop/skip links.
8. Depth-bounded propagation.
9. Shortcut/hole analysis.
10. Git-backed runtime sandboxes for branch-local execution.

## Pine Script Reference

Pine Script is a useful execution reference not just because it is compact, but because it matches the intended runtime style:

- each tick runs the same scheduler semantics
- atom/rule behavior changes according to current state/history
- outputs are naturally logged as series
- layer-by-layer replay and visualization are first-class

This is close to the intended mediator role in the new framework:

- fixed tick protocol
- reactive updates
- 2D heatmap/table outputs
- deterministic logging and replay

## Current North Star

Build a standardized upper utility layer that can map external semantic dictionaries onto per-task answer frames, expand and analyze hypotheses semantically to bounded depth, and keep all verified knowledge synchronized across:

- tables
- graphs
- semantic trees

with git branches used as reproducible runtimes for branch-local experiments rather than as the primary representation of knowledge.
