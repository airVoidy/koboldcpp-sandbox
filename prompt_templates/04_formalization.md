# Template: Formalization

## Goal

Формализовать raw atom в одну или несколько machine-usable forms.

## Output Format

```json
{
  "raw_atom": "",
  "triple": {
    "subject": "",
    "relation": "",
    "object": ""
  },
  "formal_candidates": [],
  "generalized_template": "",
  "special_cases": [],
  "rare_cases": []
}
```

## Instructions

- дай triple
- дай короткие formal candidates
- если у atom есть более общий шаблон, положи его в `generalized_template`
- если есть edge/rare cases, не теряй их

Не решай задачу целиком.
