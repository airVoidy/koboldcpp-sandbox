# Template: Chunk Question Breakdown

## Goal

Разбить один логический chunk на атомарные вопросы к нему.

## Output Format

```json
{
  "chunk_id": "",
  "questions": [
    {
      "id": "q1",
      "question": "",
      "kind": "entity|ordering|adjacency|choice|negative|structural|role"
    }
  ]
}
```

## Instructions

Для данного chunk:

- не решай задачу
- не делай длинных выводов
- просто сформулируй минимальные атомарные вопросы, на которые надо ответить, чтобы формализовать chunk

Примеры:

- "кто с кем связан?"
- "какое отношение порядка задано?"
- "это один факт или альтернатива?"
- "есть ли отрицание?"
