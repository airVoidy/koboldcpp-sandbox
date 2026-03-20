# Template: Atom Extraction

## Goal

Из одного chunk извлечь атомарные raw atoms без лишних выводов.

## Output Format

```json
{
  "atoms": [
    {
      "raw_text": "",
      "kind": "structural|ordering|adjacency|exclusive_choice|negative_constraint|role_binding|observation",
      "is_direct_text": true,
      "depends_on_interpretation": false
    }
  ]
}
```

## Instructions

- выделяй только минимальные атомы
- если в тексте два отношения, верни два атома
- если атом уже требует интерпретации, пометь `depends_on_interpretation = true`
- не подменяй raw atom formal form

Пример:

`Илья вошёл после Дианы, но до того, кто оставил записку`

должно разбиться на два atom:

- `Илья после Дианы`
- `Илья до автора`
