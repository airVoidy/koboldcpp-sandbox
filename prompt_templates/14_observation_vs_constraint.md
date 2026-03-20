# Template: Observation vs Constraint

## Goal

Определить, является ли chunk наблюдением, прямым ограничением или уже интерпретацией.

## Output Format

```json
{
  "label": "observation|constraint|interpretation",
  "reason_short": ""
}
```

## Instructions

- observation:
  - текст описывает, что кто-то заметил/обнаружил
- constraint:
  - текст прямо задает правило
- interpretation:
  - уже сделан логический переход, которого в тексте не было
