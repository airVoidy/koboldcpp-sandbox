# Template: Choice Question

## Goal

Определить, содержит ли chunk альтернативу или взаимоисключающий выбор.

## Output Format

```json
{
  "has_choice": true,
  "choice_type": "exclusive|inclusive|unknown",
  "options": []
}
```

## Instructions

- ищи конструкции типа:
  - `либо ... либо ...`
  - `или`
  - `один из`
- если это не альтернатива, а просто перечисление, верни `has_choice = false`
