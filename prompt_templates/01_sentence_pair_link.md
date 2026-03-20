# Template: Sentence Pair Link

## Goal

Определить, относятся ли два соседних предложения к одному логическому chunk.

## Input

- `sentence_a`
- `sentence_b`
- optionally: `previous_sentence`

## Output Format

```json
{
  "same_chunk": true,
  "confidence": 0.0,
  "reason_short": "",
  "relation_type": "continuation|split|example|constraint_extension|restatement"
}
```

## Instructions

Реши только одно:

- `same_chunk = true`, если второе предложение логически продолжает первое
- `same_chunk = false`, если это уже отдельное утверждение

Смотри на признаки:

- местоимения и ссылки на объект из первого предложения
- "это", "значит", "следовательно", "таким образом"
- второе предложение уточняет то же самое ограничение
- второе предложение уже начинает новое независимое правило

Отвечай строго JSON.
