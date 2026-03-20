# UV Resolver Notes For Constraint Engine

## Why `uv` is a good reference

`uv` solves a close structural problem:

- there is a global space of allowed states
- local requirements do not define truth by themselves
- the engine must find a compatible joint assignment
- when no solution exists, the system should explain why

For our project this maps well to:

- atomic QA answers -> small constraints
- deterministic assembly -> rule/constraint objects
- engine -> joint feasibility over all constraints
- user-facing output -> explained projection, not raw solver state

References:

- [uv resolver internals](https://docs.astral.sh/uv/reference/internals/resolver/)
- [uv resolution concepts](https://docs.astral.sh/uv/concepts/resolution/)
- [uv repository](https://github.com/astral-sh/uv)

## What to borrow

### 1. Incremental solver mindset

`uv` describes resolution as maintaining a partial solution and extending it step by step, with backtracking on conflicts.

For us:

- keep partial assignments / partial allowed states first-class
- do not recompute the whole world after each small answer if a local recompute is enough
- design the engine so new constraints can be appended incrementally

This matches our future need to add atomic QA answers one by one.

### 2. Prioritized decision order

`uv` explicitly says prioritization is one of the most important heuristics for both performance and UX.

For us this suggests:

- choose the next variable / fragment / unresolved slot by heuristic priority
- prefer highly constraining facts first
- prefer exact and structural constraints before weaker interpretive ones

Good first heuristic order for our puzzle-like cases:

1. structural
2. exact position / count
3. adjacency
4. ordering
5. negation
6. soft or derived observations

### 3. Conflict explanation as a first-class output

`uv` does not stop at `UNSAT`; it tracks incompatibilities and builds an understandable error trace.

For us this is directly relevant:

- a contradiction should point back to rule ids
- rule ids should point back to `source_ref`
- a blocked segment or impossible hypothesis should carry a blocking explanation

This strongly supports our existing direction:

- canonical `source_ref`
- future `ProvenanceGraph`
- future `BlockingExplanation` / `SupportExplanation`

### 4. Keep source of truth separate from summary

`uv` internally tracks the resolution state, while the final human-facing explanation is derived from it.

For us:

- source of truth = variables, rules, AST, provenance, solver state
- summary = ranges, candidate orders, anomalies, explanations

We should not treat `questions_v0.json`, `crosschecks_v0.json`, or future range summaries as truth.

### 5. Stable preferences and deterministic replay

`uv` uses preferences from prior lockfiles and installed versions to keep resolutions stable.

For us the analogous idea is:

- stable rule ids
- stable object/relation ids
- stable provenance ids
- deterministic ordering of generated constraints

This will matter once the same case is reprocessed after parser improvements or extra QA passes.

### 6. Forking is conceptually useful

`uv` forks resolution when marker conditions split the space.

We likely do not need full fork machinery yet, but the idea is useful:

- choice constraints (`either/or`)
- alternative interpretations
- unresolved role bindings

These can be modeled as branch points over the same base constraint store.

For our domain, this is closer to:

- branch candidates
- grouped hypothesis seeds
- alternate author assignments

## What not to copy

- package/version semantics
- semver-specific logic
- wheel/platform marker machinery
- lockfile-specific persistence model
- package registry and metadata fetch behavior

Those are domain-specific and would add noise.

## Practical mapping to our repo

Current artifacts:

- `raw_claims.json` -> candidate user/source rules
- `atoms_v0.json` -> small normalized constraints
- `source_ref` -> provenance leaf

Next engine layer:

- `Variable`
- `Rule`
- minimal `Expr` / `Pred` AST
- `ConstraintStore`
- `DependencyIndex`
- `ProvenanceGraph`
- narrow `SolverAdapter`

Only after that:

- `ProjectionAnalyzer`
- explained ranges / allowed segments
- support vs blocking explanations

## MVP interpretation for `quest_order_case`

We should not begin with a general symbolic engine for everything.

Start with a narrow constraint core for:

- `pos(person) = integer`
- uniqueness of positions
- `before`
- `after`
- `immediately_after`
- `not_position(first)`
- `either(first,last)`

Then add provenance:

- every rule has `rule_id`
- every rule links to one or more `source_ref`
- every contradiction or derived exclusion returns supporting rule ids

That already gives us a usable first engine.

## Concrete lessons from `uv`

If I compress the useful lessons into one implementation rule:

> Build the next layer as an incremental, explanation-preserving constraint engine, not as a pile of derived JSON summaries.

That is the part worth copying from `uv`.
