# Template: Negation Question

## Goal

Определить, есть ли в chunk отрицание.

## Output Format

```json
{
  "has_negation": true,
  "negated_targets": []
}
```

## Instructions

- ищи `не`, `нельзя`, `невозможно`, `не был`, `не вошла`
- верни только то, что прямо отрицается
