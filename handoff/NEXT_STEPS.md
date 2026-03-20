# Next Steps

## Ближайшие практические шаги

1. Выравнять все example-файлы под единый `source_ref` schema.
2. Добавить `sentence_id` и `fragment_id` в objects / relations / atoms.
3. Улучшить deterministic parser:
   - не тащить лишний setup в один fragment
   - лучше делить ordering sentences на sub-fragments
   - лучше bucket-ить choice / ordinal / role cases
4. Сделать первый локальный QA runner:
   - берет fragment
   - запускает 3-6 micro-templates
   - собирает merged result локальным кодом
5. Добавить `unresolved_tail_v0.json`
6. Добавить `grouped_hypothesis_seeds_v0.json`
7. Начать первый minimal wrapper поверх `pynecore` для tick + fragment emission

## Жесткие правила

- маленькие модели отвечают только атомарно
- JSON собирает код
- relation buckets должны быть узкими
- лишнюю метадату лучше сохранить, чем потерять
- source provenance обязателен
