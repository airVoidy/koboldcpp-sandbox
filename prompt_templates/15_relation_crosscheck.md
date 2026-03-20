# Template: Relation Crosscheck

## Goal

Проверить relation в обе стороны между двумя объектами/группами.

## Output Format

```json
{
  "forward_true": true,
  "backward_true": true,
  "forward_relation": "",
  "backward_relation": "",
  "confidence": 0.0
}
```

## Instructions

Проверяй пары вроде:

- `[$Лера] относится к группе [$друзей]?`
- `группа [$друзей] включает [$Лера]?`

Отвечай только по текущему тексту.
Не додумывай лишнего.
