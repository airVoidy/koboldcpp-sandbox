# Template: Interpretation Guard

## Goal

Понять, является ли candidate atom прямым текстом или уже derived interpretation.

## Output Format

```json
{
  "is_direct_text": true,
  "needs_interpretation": false,
  "interpretation_level": "none|light|strong",
  "reason_short": ""
}
```

## Instructions

Пример:

- `Диана не вошла первой` -> direct text
- `author < 5` из фразы про пятого посетителя -> interpretation

Нужно только классифицировать степень интерпретации.
