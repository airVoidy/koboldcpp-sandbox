# Step Progress

Date: 2026-03-14

## What was completed

- Added 2D assertion board and hypothesis tree layer.
- Added structured constraint AST and later introduced rule DSL for relative/absolute rules.
- Added reactive atom runtime and API for atom evaluation.
- Added hypothesis runtime with:
  - connected-component evaluation
  - automatic dependency graph
  - API endpoint for connected hypothesis evaluation
- Added artifact/effect model based on state transformations.
- Added branch outcome / step snapshot writer.
- Added LLM-friendly step output renderer (`python` block + summary).
- Created and evolved Einstein as the main live example.
- Moved Einstein example-specific tests to `examples/einstein_case/tests/`.
- Added top-level aggregated Einstein suite in `.tests/einstein_case/`.
- Saved latest pytest outputs in text files.

## Current architecture status

### Core layers present

- Assertions / hypothesis tree
- Constraint AST
- Rule DSL (`ref`, `eq`, `next_to`, `right_of`, etc.)
- Reactive atom runtime
- Hypothesis runtime
- Effect artifacts
- Branch outcomes / step snapshots
- Einstein example with first reactive step

### What is already automated

- Einstein direct givens build from inventory.
- Einstein relation clues build from inventory.
- Einstein first-step tree builds from node specs inventory.
- Einstein first-step direct effects build from givens inventory.
- Relative checks like `norwegian-next-to-blue` use DSL + runtime functions instead of handwritten per-hypothesis helper functions.

## Test status

Latest verified suite:
- `27 passed`

Relevant output files:
- `.tests/latest_pytest_output.txt`
- `examples/einstein_case/tests/latest_pytest_output.txt`
- `.tests/einstein_case/latest_pytest_output.txt`

## Important files added/changed in this step

- `src/kobold_sandbox/assertions.py`
- `src/kobold_sandbox/constraints.py`
- `src/kobold_sandbox/rule_dsl.py`
- `src/kobold_sandbox/rule_runtime.py`
- `src/kobold_sandbox/reactive.py`
- `src/kobold_sandbox/hypothesis_runtime.py`
- `src/kobold_sandbox/artifacts.py`
- `src/kobold_sandbox/outcomes.py`
- `src/kobold_sandbox/einstein_example.py`
- `src/kobold_sandbox/server.py`
- `src/kobold_sandbox/storage.py`
- `ARTIFACT_SCHEMA.md`
- `API_EXAMPLES.md`
- `WORKER_OUTPUT_FORMAT.md`
- `MANUAL_COMPLEXITY_AUDIT.md`

## Remaining rough edges accepted for now

- Einstein inventories still live in Python constants, not external data files.
- Structural claim generation still lives in code.
- Quest-order runtime effect example is still hand-authored.
- `.tests` still duplicates the Einstein suite for top-level aggregation.
- Worker output formatting is still template-based, not category-aware.
