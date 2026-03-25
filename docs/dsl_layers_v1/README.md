# DSL Layers V1

Reference bundle for the planned 3-layer DSL architecture:

- `GUI DSL` for view/layout/bindings/actions
- `Atomic DSL` for data/runtime substrate
- `Workflow DSL` for orchestration

This folder is an architectural example and orientation point, not an enforced implementation yet.

## Files

- [LAYER_MAP.md](/C:/llm/KoboldCPP%20agentic%20sandbox/docs/dsl_layers_v1/LAYER_MAP.md)
- [BRIDGE_SPEC_V1.md](/C:/llm/KoboldCPP%20agentic%20sandbox/docs/dsl_layers_v1/BRIDGE_SPEC_V1.md)
- [bridge_models.py](/C:/llm/KoboldCPP%20agentic%20sandbox/docs/dsl_layers_v1/bridge_models.py)
- [macro_registry.json](/C:/llm/KoboldCPP%20agentic%20sandbox/docs/dsl_layers_v1/macro_registry.json)

## Intent

- keep `Workflow` free from low-level data mutations
- keep `Atomic` as the canonical data and execution substrate
- keep `GUI` declarative and bound to state/entities
- make saved macros reusable from both `Atomic` and `Workflow`

## Bridge Surface

- `use_macro`
- `atomic`
- `trigger_workflow`
- `run_macro`
- `run_atomic`

Current implementation:
- `use_macro` is wired in `workflow_dsl.py`
- `atomic` supports isolated inline `flow`, `steps`, and `dsl`
- shared macro records now carry metadata like `layer`, `inputs`, `outputs`, `tags`, `description`, `workflow_alias`
- Atomic UI exposes a separate `Metadata` tab for macro records

## Canonical Builtins

Current builtin-oriented macro names:
- `constraints_manifest`
- `answer_constraints_verdict`
- `hypothesis_verdict`
