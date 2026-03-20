# Template: Ordering Question

## Goal

Понять, задает ли chunk отношение порядка.

## Output Format

```json
{
  "has_ordering": true,
  "ordering_relations": [
    {
      "left": "",
      "relation": "before|after",
      "right": ""
    }
  ]
}
```

## Instructions

- выделяй только прямые отношения порядка
- если их нет, верни пустой список
- не превращай наблюдение в вывод
