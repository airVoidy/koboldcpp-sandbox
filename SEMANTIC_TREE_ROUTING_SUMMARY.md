# Semantic Tree Routing Summary

## Why Semantic Trees Were Chosen

Semantic trees are not used here just because they are expressive.

They are used because they are practical carriers for:

- semantic structure
- route tracing
- backward analysis
- shortcut discovery
- constrained retrospective search

## Meaning of "Ternary" in This Project

Important clarification for agent-facing consistency:

In this project, `ternary` should primarily be understood in the operational semantic sense:

- `push`
- `pop`
- `skip`

That is:

- descend into local consequence structure
- return to prior context
- move to sibling / alternate / neighbor route

This is the default intended meaning unless a narrower mathematical/topological meaning is explicitly stated.

Reason:

- humans often pattern-match the intended abstraction from context
- agents may over-fix on a narrower structural interpretation
- the framework is being designed for agent use, so this ambiguity must be removed explicitly

So in this codebase and its docs:

- `ternary semantics` = push/pop/skip traversal semantics by default
- stricter meanings should be named explicitly when needed

In other words, semantic trees are useful here for the same family of reasons they are useful in routing and trace-style IT tasks:

- they preserve path structure
- they support directional traversal
- they make forward and backward search natural
- they allow pruning and route masking

## Practical Role in This Framework

Within this project, a semantic tree should serve three jobs at once:

1. Store ternary semantic content.
2. Provide navigable reasoning structure.
3. Act as a route space for optimization and retrospective analysis.

So the semantic tree is both:

- a meaning structure
- a routing substrate

## Forward and Backward Use

### Forward

Use the tree to expand:

- from atomic hypotheses
- to grouped hypotheses
- to derived consequences

### Backward

Use the tree to search:

- from deep derived structures
- back to minimal supporting inputs
- while excluding or penalizing unwanted routes

This lets the framework:

- find shortest useful derivations
- identify missing minimal trees
- generate shortcut hypotheses
- avoid noisy or low-value explanation paths

## Route Control

One of the main advantages is that routes do not have to stay equally available.

The framework should be able to mark routes as:

- allowed
- forbidden
- discouraged
- expensive
- preferred

That enables retrospective optimization from `12 -> 1` while preserving normal forward reasoning from `1 -> 12`.

## Relationship to Matrices and Graphs

The intended split is:

- semantic tree: route space
- causal graph: dependency/support/conflict structure
- matrix: coverage geometry and per-step state logging

This is why all three are required.

## Why This Matters

Because the same atomic hypotheses can combine into different grouped hypotheses, and those grouped hypotheses can produce different coverage zones, we need:

- trees for traversable route structure
- graphs for causal links
- matrices for coverage and stepwise logging

## Working Design Principle

Semantic tree is chosen here not as a decorative representation, but as an operational runtime layer for:

- trace
- reverse trace
- route masking
- shortcut search
- minimal-support discovery

## Immediate Todo

1. Define minimal semantic-tree node schema with `subject/relation/object`.
2. Define route-edge semantics: `push`, `pop`, `skip`, `forbidden`, `preferred`, `shortcut`.
3. Define backward-route query format for `12 -> 1` retrospective search.
4. Define how shortcut hypotheses are emitted from route optimization.
5. Define matrix projection fields for per-tick and per-layer coverage logging.
6. Define sync rules between tree routes, causal graph edges, and matrix patches.
7. Build a tiny toy case that demonstrates:
   - forward expansion
   - backward route masking
   - shortcut discovery
