# Manual Complexity Audit

Ниже перечислены места, где на текущем этапе still есть ручное описание логики, которое желательно со временем упростить для автоматического/LLM-парсинга.

## High Priority

### Einstein inventory still lives in Python, not in external data

File:
- [einstein_example.py](C:/llm/KoboldCPP%20agentic%20sandbox/src/kobold_sandbox/einstein_example.py)

Manual parts:
- `DIRECT_GIVENS`
- `RELATION_CLUES`
- `FIRST_STEP_NODE_SPECS`

Why it is manual:
- inventory уже data-driven, но все еще захардкожен в Python
- parser/loader пока не подгружает это из внешних artifacts

Refactor direction:
- хранить clue inventory в data file
- загружать first-step hypothesis inventory из artifacts

### Structural claims still compile from loops inside code

File:
- [einstein_example.py](C:/llm/KoboldCPP%20agentic%20sandbox/src/kobold_sandbox/einstein_example.py)

Manual parts:
- `_build_structural_claims()`

Why it is manual:
- logic is generic, but source inventory still generated directly in Python

Refactor direction:
- move structural templates into reusable generator layer or artifact schema

## Medium Priority

### Quest runtime effect example

File:
- [quest_order_runtime.py](C:/llm/KoboldCPP%20agentic%20sandbox/src/kobold_sandbox/quest_order_runtime.py)

Manual parts:
- `derive_corridor_effect_artifact()`

Why it is manual:
- artifact и candidate cloud заданы вручную
- good as reference, but not scalable

Refactor direction:
- runtime callable should compute output from context
- artifact writer should serialize computed transformations

### Outcome rendering

File:
- [outcomes.py](C:/llm/KoboldCPP%20agentic%20sandbox/src/kobold_sandbox/outcomes.py)

Manual parts:
- `render_llm_step_output(...)`

Why it is manual:
- fixed output template
- no distinction yet between:
  - fixed cells
  - narrowed domains
  - contradictions
  - derived constraints

Refactor direction:
- render from structured effect categories
- optionally expose multiple worker-oriented templates

## Lower Priority

### Hypothesis API payload assembly

File:
- [server.py](C:/llm/KoboldCPP%20agentic%20sandbox/src/kobold_sandbox/server.py)

Manual parts:
- `_claim_stub(...)`
- payload-to-tree reconstruction in `/hypotheses/evaluate-connected`

Why it is manual:
- useful for now
- but eventually should compile from stored branch artifacts / DSL rules

Refactor direction:
- load branch/hypothesis state from node artifacts
- avoid reconstructing tree ad hoc from raw request JSON

### Test duplication for example aggregation

Files:
- [test_einstein_example.py](C:/llm/KoboldCPP%20agentic%20sandbox/examples/einstein_case/tests/test_einstein_example.py)
- [test_einstein_case_suite.py](C:/llm/KoboldCPP%20agentic%20sandbox/.tests/einstein_case/test_einstein_case_suite.py)

Why it is manual:
- top-level `.tests` currently duplicates example-local tests

Refactor direction:
- eventually use a custom collector or explicit suite runner
- for now duplication is acceptable for navigation and stability

## Good News

Already reduced manual burden:
- relative/absolute hypothesis checks can now use:
  - [rule_dsl.py](C:/llm/KoboldCPP%20agentic%20sandbox/src/kobold_sandbox/rule_dsl.py)
  - [rule_runtime.py](C:/llm/KoboldCPP%20agentic%20sandbox/src/kobold_sandbox/rule_runtime.py)
- `ReactiveAtom.from_rule(...)` removes the need for per-hypothesis handwritten functions in many cases
- Einstein direct givens, relation clues, first-step tree, and first-step effects now build from inventory records instead of one-off handwritten assembly

## Recommended Next Refactors

1. Move Einstein inventory from Python constants into declarative data/artifacts.
2. Generate `EffectArtifact` from runtime outputs instead of partially inventory-driven effects.
3. Add a loader that compiles example artifacts into rules/hypotheses automatically.
4. Replace duplicated example suite files in `.tests` with a custom collector/suite runner.
