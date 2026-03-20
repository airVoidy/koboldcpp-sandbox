# Next Step Plan

## Goal

Continue removing manual assembly and move toward artifact-driven generation for examples, starting with Einstein.

## Recommended order

1. Externalize Einstein inventory
- Move `DIRECT_GIVENS`, `RELATION_CLUES`, and `FIRST_STEP_NODE_SPECS` into data/artifact files.
- Add loader: `artifact/data -> Rule/Hypothesis/Effect inventory`.

2. Reduce manual structural generation
- Replace `_build_structural_claims()` with reusable generator config or artifact schema.
- Keep support for `exactly_one` / `all_different` through DSL or generator templates.

3. Auto-build step effects from runtime outputs
- Instead of inventory-generated first-step effects, derive them from runtime result where possible.
- Feed them directly into `EffectArtifact` generation.

4. Improve worker output
- Make `render_llm_step_output(...)` category-aware:
  - fixed cells
  - narrowed domains
  - candidate clouds
  - contradictions
  - derived constraints

5. Optional cleanup
- Replace duplicated `.tests` example suite with a dedicated collector/suite runner.

## Concrete first task for next chat

Start with Einstein inventory externalization:
- create example-local data file(s) under `examples/einstein_case/`
- load them into `einstein_example.py`
- keep existing tests green

## Constraints to remember

- Prefer DSL/rule inventory over handwritten per-hypothesis functions.
- Keep reactive runtime as the execution layer.
- Keep output compatible with LLM workers: Python block + short structured summary.
- Keep example-specific tests near the example source of truth.

## Added handoff note
- See internal_git_format.md before starting the next implementation step.

