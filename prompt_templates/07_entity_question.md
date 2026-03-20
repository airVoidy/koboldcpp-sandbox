# Template: Entity Question

## Goal

Понять, вводит ли chunk новые сущности или роли.

## Output Format

```json
{
  "entities": [],
  "roles": [],
  "introduces_new_entities": false
}
```

## Instructions

- выделяй только сущности и роли
- ничего не выводи сверх текста
- если сущность уже известна, все равно можно вернуть ее в списке
