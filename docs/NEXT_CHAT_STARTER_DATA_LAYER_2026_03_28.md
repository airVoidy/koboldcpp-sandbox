# Next Chat Starter — Atomic Data Layer / Assembly

Скопируй это как первое сообщение в новом чате.

---

Прочитай для контекста:

- [ATOMIC_TRANSFER_CONTEXT.md](C:\llm\KoboldCPP agentic sandbox\docs\ATOMIC_TRANSFER_CONTEXT.md)
- [ATOMIC_OBJECT_MAP_V0_1.md](C:\llm\KoboldCPP agentic sandbox\docs\ATOMIC_OBJECT_MAP_V0_1.md)
- [ATOMIC_DECLARATIVE_EVENT_DSL_V0_1.md](C:\llm\KoboldCPP agentic sandbox\docs\ATOMIC_DECLARATIVE_EVENT_DSL_V0_1.md)
- [ASSEMBLY_DSL_SPEC_V0_1.md](C:\llm\KoboldCPP agentic sandbox\docs\ASSEMBLY_DSL_SPEC_V0_1.md)
- [ATOMIC_DATA_SCOPE_NAMESPACE_V0_1.md](C:\llm\KoboldCPP agentic sandbox\docs\ATOMIC_DATA_SCOPE_NAMESPACE_V0_1.md)
- [ATOMIC_DATA_SCOPE_LIFECYCLE_V0_1.md](C:\llm\KoboldCPP agentic sandbox\docs\ATOMIC_DATA_SCOPE_LIFECYCLE_V0_1.md)
- [ATOMIC_WIKI_CONTAINER_REF_MODEL_V0_1.md](C:\llm\KoboldCPP agentic sandbox\docs\ATOMIC_WIKI_CONTAINER_REF_MODEL_V0_1.md)
- [ATOMIC_MESSAGE_ANNOTATIONS_V0_1.md](C:\llm\KoboldCPP agentic sandbox\docs\ATOMIC_MESSAGE_ANNOTATIONS_V0_1.md)
- [ATOMIC_REVISION_PERSISTENCE_POLICY_V0_1.md](C:\llm\KoboldCPP agentic sandbox\docs\ATOMIC_REVISION_PERSISTENCE_POLICY_V0_1.md)

Текущая фиксация архитектуры:

- `workflow/v2` остаётся orchestration DSL
- новый Atomic слой сейчас делаем отдельно для `Data Layer + Assembly`
- верхний namespace: `data/...`
- scope lifecycle:
  - `@data.temp`
  - `@data.local`
  - `@data.global`
- `wiki` не верхний namespace, а text-oriented data template внутри `data/...`
- `wiki` refs считаем container-level, не field-level
  - лучше `@data.local.wiki.task.input`
  - хуже `@data.local.wiki.task.input.text`
- доступ к внутренностям wiki лучше делать вторым шагом:
  - `read_text(...)`
  - `resolve_slot(...)`
  - `project_table(...)`

Практически уже сделано в коде:

- `src/kobold_sandbox/event_dsl.py`
  - compile-only `emit/on -> assembly`
- `src/kobold_sandbox/workflow_dsl.py`
  - `GEN` modes:
    - `live`
    - `mock`
    - `fixture`
    - `replay`
- `src/kobold_sandbox/atomic_table_object.py`
  - jsonlike -> table object mid-layer
- `src/kobold_sandbox/atomic_annotations.py`
  - `message -> annotation rows`
  - row patch обратно в message annotations
  - collect unique values
  - build / merge wiki-like summary message
- `src/kobold_sandbox/atomic_dsl_api.py`
  - `/api/dsl/event/compile`
  - `/api/dsl/annotations/wiki/build`
  - `/api/dsl/annotations/wiki/merge`
- `src/kobold_sandbox/atomic_data_revision.py`
  - git-backed data text artifacts + revision manifest
  - но это считать backend capability для maintenance/persistence passes, не default side-effect DSL

Важная policy:

- revision persistence не вшивать в каждый `emit/on` шаг
- сначала runtime / data transforms
- потом отдельные passes:
  - integrity verify
  - garbage collect
  - local -> global promote
  - revision commit

Текущий practical direction:

- text-like durable data живёт как message/wiki-like artifacts
- objects/tables/checkpoints живут как operational structured layer
- объекты в revision layer можно не хранить целиком, только их хеши
- `workflow/v2` использовать там, где нужны orchestration/think probes
- всё, что можно, стараться держать на Data Layer + Assembly

Полезный рабочий кейс:

- размечать в текстах блоки про цвет глаз и волос
- вытаскивать значения через annotations
- собирать локальный или глобальный wiki-like summary с source refs

Следующий шаг в новом чате:

- не плодить новые большие спеки
- спуститься в практику и решить один маленький end-to-end кейс на `Data Layer + Assembly`
- если где-то не хватает выразительности, аккуратно доращивать DSL снизу
