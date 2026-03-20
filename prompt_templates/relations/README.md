# Relation Buckets

Идея:

- сначала не "понимать все"
- сначала находить самые простые relation-patterns
- раскладывать предложения/фрагменты по relation buckets
- в каждой папке держать:
  - признаки матчинга
  - простые yes/no вопросы
  - базовые extraction rules
  - кейсы из examples

Пайплайн:

1. sentence split
2. sentence fragments
3. primitive relation match
4. dispatch into bucket folder
5. bucket-specific extraction
6. unresolved tail -> manual / bigger LLM

Главное правило:

- relation bucket должен отвечать на один очень узкий вопрос
- JSON собирает локальный код
- маленькая модель отвечает только коротко

## Reliability Add-on

Для relation buckets стоит постепенно хранить:

- positive examples
- wrong-answer probes
- anomaly markers

Если точность bucket classifier недостаточна, лучше делать избыточные пересечения и проверки, чем один хрупкий проход.

Особенно важно хайлайтить:

- противоречия
- несовместимые relation labels
- неожиданные bucket overlaps
- unresolved fragments

## Initial Buckets

- `entities`
- `ordering_after_before`
- `adjacency_immediate`
- `choice_either_or`
- `negation_not`
- `ordinal_position`
- `observation_state`
- `role_mentions`
- `structural_once_individual`
- `unresolved`
