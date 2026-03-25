# Bridge Spec V1

Minimal bridge contract between `GUI DSL`, `Workflow DSL`, and `Atomic DSL`.

## Core Rules

- `bind` always maps `callee_input -> caller_expr`
- `export` always maps `caller_target <- callee_output`
- `use_macro` and `run_macro` use macro registry
- `atomic` and `run_atomic` run inline Atomic DSL
- `trigger_workflow` executes a named Workflow trigger

## 1. Workflow -> use_macro

```yaml
- use_macro:
    name: answer_constraints_verdict
    bind:
      input: $input
    export:
      $accepted: accepted
      $rejected: rejected
      $table: table_text
```

Rules:
- macro runs in an isolated Atomic scope
- only declared `export` values leave that scope

## 2. Workflow -> atomic

```yaml
- atomic:
    bind:
      input: $input
    flow:
      - analyzer -> $claims:
          prompt: claims($input)
          temperature: 0.1
          max_tokens: 2048
      - parse_claims:
          from: $claims
          export: [$entities, $axioms, $hypotheses]
    export:
      $entities: entities
      $axioms: axioms
```

Current implementation note:
- `flow:` and `steps:` are supported now through isolated child execution
- `dsl:` is supported now through the inline Atomic DSL bridge

## 3. GUI -> trigger_workflow

```yaml
action:
  type: trigger_workflow
  name: check
  bind:
    input: @form.prompt
```

## 4. GUI -> run_macro

```yaml
action:
  type: run_macro
  name: hypothesis_verdict
  bind:
    prompt: @form.prompt
  export:
    @view.hyp_table: hyp_table_text
```

## 5. GUI -> run_atomic

```yaml
action:
  type: run_atomic
  dsl: |
    @claims = generate(@input, worker:analyzer)
  bind:
    input: @form.prompt
  export:
    @view.claims: claims.answer
```

## Macro Registry Shape

```json
{
  "name": "answer_constraints_verdict",
  "layer": "atomic",
  "inputs": ["prompt", "prompt_constraints_strict", "target_rows", "max_table_iters"],
  "outputs": ["accepted", "rejected", "table_text"],
  "tags": ["verdict", "table", "builtin"],
  "description": "Parallel answer + constraints pipeline that builds a verdict table and accepted/rejected lists.",
  "dsl": "..."
}
```

Legacy string macros may still be read as:
- `layer: "atomic"`
- empty `inputs`
- empty `outputs`

## Dataclass Form

```python
from dataclasses import dataclass, field
from typing import Literal

BridgeKind = Literal[
    "use_macro",
    "atomic",
    "trigger_workflow",
    "run_macro",
    "run_atomic",
]

@dataclass
class ExportBinding:
    target: str
    source: str

@dataclass
class BaseBridge:
    type: BridgeKind
    bind: dict[str, str] = field(default_factory=dict)
    export: list[ExportBinding] = field(default_factory=list)

@dataclass
class UseMacroBridge(BaseBridge):
    type: Literal["use_macro"] = "use_macro"
    name: str = ""

@dataclass
class AtomicBlockBridge(BaseBridge):
    type: Literal["atomic"] = "atomic"
    dsl: str = ""

@dataclass
class TriggerWorkflowBridge(BaseBridge):
    type: Literal["trigger_workflow"] = "trigger_workflow"
    name: str = ""

@dataclass
class RunMacroBridge(BaseBridge):
    type: Literal["run_macro"] = "run_macro"
    name: str = ""

@dataclass
class RunAtomicBridge(BaseBridge):
    type: Literal["run_atomic"] = "run_atomic"
    dsl: str = ""
```
