# Template: Group Membership

## Goal

Определить, описывает ли chunk отношение membership между group и entity.

## Output Format

```json
{
  "has_membership": true,
  "group_phrase": "",
  "member_phrases": []
}
```

## Instructions

- ищи конструкции перечисления после group noun
- если группа названа, а участники перечислены, верни group + members
- не формализуй пока cardinality сверх прямого текста
