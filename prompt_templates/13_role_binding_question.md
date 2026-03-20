# Template: Role Binding Question

## Goal

Определить, связывает ли chunk роль с сущностью или с неизвестным объектом.

## Output Format

```json
{
  "has_role_binding": true,
  "bindings": [
    {
      "role": "",
      "target": ""
    }
  ]
}
```

## Instructions

- examples:
  - `тот, кто оставил записку`
  - `автор записки`
  - `пятый посетитель`
- если role mention есть, но binding не фиксирован, все равно верни ее как role target
