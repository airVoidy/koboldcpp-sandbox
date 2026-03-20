# Template: Adjacency Question

## Goal

Определить, задает ли chunk соседство/непосредственное следование.

## Output Format

```json
{
  "has_adjacency": true,
  "adjacency_relations": [
    {
      "left": "",
      "relation": "immediately_after|immediately_before|adjacent_to",
      "right": ""
    }
  ]
}
```

## Instructions

- примеры маркеров:
  - `сразу после`
  - `сразу перед`
  - `рядом`
