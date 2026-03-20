# Artifact Schema

Минимальная схема для semantic merge / branch outcomes.

## Principle

- `outcome.json` должен быть индексом
- детальные артефакты хранятся отдельно
- эффекты моделируются как `state transformation`

## Suggested Layout

```text
analysis/
  outcome.json
constraints/
  c-0001.json
atoms/
  a-0001.json
effects/
  e-0001.json
reasoning/
  r-0001.md
```

## State Transformation

Базовая единица эффекта:

- `subject_ref`
- `previous_domain_ref`
- `next_domain_ref`
- `justification_refs`

Это позволяет одинаково описывать:

- fixed assignment
- range narrowing
- candidate clouds
- contradictions
- branch splits

## Why Not target=value

Плоская модель `target=value` слишком узкая.

Реальный runtime output может быть:

- singleton
- interval
- set
- candidate cloud
- derived constraint
- branch proposal

Поэтому effect artifact должен описывать не scalar assignment, а преобразование состояния.
