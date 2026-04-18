# Session Notes: Virtual Container / Lambda Batch Discussion

Date: 2026-04-18

## Main direction

- The framework should be coverage-first and projection-first, not a linear workflow DSL.
- Workflow instances are not singletons; each is a canonical atomic path projection.
- Detached fields are the substrate; virtual containers are cheap recompositions over them.
- Branching should be represented as projection/tag layers and shadow virtual objects, not graph explosion.
- Methods are better modeled as edges/transforms over required field sets than as object methods.
- The system is closer to a lambda batch resolver than to a classic runtime graph.

## Key ideas

- Declarative checkpoint relation plus local resolver:
  - `messages -> messages[reactions[:thumbsupp:]]`
  - `:: each message add reaction(:thumbsupp:)`
- Unresolved residue is first-class:
  - missing fields
  - branch candidates
  - invariants
  - anomaly tags
- Branches can live as shadow wrappers inside the same container and be viewed by projection switching.
- Shadow virtual objects let alternative paths stay linear and comparable during prototyping.
- Containers can be grouped structurally by a union hash / normalized schema signature.
- If two branches converge structurally, their container families can collapse again.

## Resolve model

- Not purely left-to-right.
- Not simply right-to-left.
- Better described as perpendicular / bidirectional saturating resolve on each node.
- Every pass can:
  - cast neighbor transforms
  - compare outputs
  - mark anomalies
  - add fields
  - add branches
  - propagate invariants backward
  - propagate fields forward
- Repeat until local or global fixpoint.

## Coverage and synthetic-first strategy

- Minimize generator work by doing everything possible structurally first.
- Use synthetic value representations for fields and containers.
- Precompute branch-space and likely return-shape families before expensive worker use.
- Real worker responses should be matched against already known expected shape classes.
- Exceptions should become typed problem objects where possible.
- Background workers can explore unresolved points, prompt variants, or repair slices without blocking the main workflow.

## Architecture projection

- Architecture should exist as a semantic projection over the same container/code structure.
- It does not need full auto-resolution to be useful.
- It should serve as:
  - sanity-check
  - drift detector
  - local rationale carrier
- Markdown notes alone are too lossy and drift away from local code context.

## Code / MCP-IDE angle

- Containerized code editing can solve a major agent pain point:
  - stable structural selection
  - safe local patching
  - breakage detection before total collapse
- Git should keep projected code state for humans.
- Shadow/container structure should exist in sidecar form for agents.
- Structural breakage can be shown as projection mismatch instead of raw line-offset failure.

## Invariant subscription idea

- Real-time subscriptions over agreements/invariants may be a major win.
- Even tiny smoke specs could bind to projections at entrypoints and enforce agreements.
- Example:
  - one user action corresponds to one `exec()`

## Long-term idea

- DSL over DSL over DSL cyclic routing:
  - problem/intention layer
  - architecture layer
  - schema atom layer
  - code materialization layer
- The framework is mainly a utility for solution-space coverage and reasoning support, not a strict execution language.

## Practical note

- One visible object should collapse to naming + display.
- Hidden resolution state should stay in sidecar/shadow layers.
- A universal atom / scope carrier may be enough:
  - scope in
  - operation
  - scope out

