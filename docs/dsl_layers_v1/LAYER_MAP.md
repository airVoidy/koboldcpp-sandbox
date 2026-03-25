# Layer Map

## GUI DSL

Purpose:
- describe screens, cards, lists, buttons, forms
- bind widgets to state/entity paths
- dispatch actions into lower layers

Should know about:
- `@view.*`
- `@form.*`
- action names
- display metadata

Should not know about:
- worker routing
- prompt internals
- parsing details

## Atomic DSL

Purpose:
- hold and mutate runtime data
- execute low-level generation and transform primitives
- manage entity graph and local scopes

Should know about:
- entities
- text areas / tables / lists
- transforms
- loops / guards / scopes
- config refs

Canonical responsibilities:
- `generate`
- `parse_sections`
- `parse_table`
- `set_text`
- `append_text`
- transforms like `split`, `join`, `chunk`, `reshape`
- macro registry records and metadata for reusable Atomic building blocks

## Workflow DSL

Purpose:
- orchestrate higher-level scenarios
- compose parallel steps, loops, triggers, routing

Should know about:
- `let`
- `flow`
- `in_parallel`
- `for`
- `triggers`
- worker roles
- bridge calls into Atomic

Should not own:
- data graph structure
- UI layout bindings
- low-level parsing/transforms as hardcoded behavior

## Canonical Direction

```text
GUI DSL -> Workflow DSL -> Atomic DSL
GUI DSL -> Atomic macro
```

## Why Atomic Has Loops

Atomic loops are local runtime control:
- continue until row target
- repeat probe until bounded condition
- iterate data mutations in a scope

This is different from reactive/entity propagation loops and does not conflict with them.

## Migration Principle

Move hardcoded workflow helpers toward:
- atomic stdlib
- atomic macro library
- explicit bridges

Leave in Workflow only:
- orchestration
- routing
- trigger composition

## Shared Macro Registry

Macro records should be reusable across layers:
- `Atomic UI` can save, rename, delete, import, export, and edit metadata
- `Workflow DSL` can call them through `use_macro`
- canonical metadata shape includes:
  - `name`
  - `layer`
  - `inputs`
  - `outputs`
  - `tags`
  - `description`
  - `workflow_alias`
