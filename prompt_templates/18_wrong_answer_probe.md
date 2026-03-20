# Template: Wrong Answer Probe

## Goal

Сгенерировать явно неправильный ответ на узкий вопрос, чтобы хранить рядом positive/negative examples.

## Output Format

```json
{
  "question": "",
  "wrong_answer": "",
  "why_wrong_short": ""
}
```

## Instructions

- дай один короткий, но явно неправильный ответ
- он должен противоречить тексту или relation bucket
- не придумывай длинные объяснения
- нужен именно negative sample

## Example

Question:

- `Есть ли отрицание?`

Wrong answer:

- `no`

If text is:

- `Диана не вошла первой`
