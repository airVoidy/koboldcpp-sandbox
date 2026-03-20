# Current State

## Что уже сделано

- Зафиксирована общая архитектура, series runtime, semantic tree routing, probability bridge и pynecore integration.
- Для `examples/quest_order_case` сделан первый alpha-pass метадаты.
- Создана relation-bucket структура и prompt templates для маленьких моделей.
- Добавлен очень простой deterministic parser без LLM.

## Главная рабочая точка сейчас

Кейс:

- [quest_order_case](C:\llm\KoboldCPP agentic sandbox\examples\quest_order_case)

Ключевые файлы:

- [answer_frame.json](C:\llm\KoboldCPP agentic sandbox\examples\quest_order_case\answer_frame.json)
- [raw_claims.json](C:\llm\KoboldCPP agentic sandbox\examples\quest_order_case\raw_claims.json)
- [atoms_v0.json](C:\llm\KoboldCPP agentic sandbox\examples\quest_order_case\atoms_v0.json)
- [relation_buckets_v0.md](C:\llm\KoboldCPP agentic sandbox\examples\quest_order_case\relation_buckets_v0.md)
- [objects](C:\llm\KoboldCPP agentic sandbox\examples\quest_order_case\objects)
- [relations](C:\llm\KoboldCPP agentic sandbox\examples\quest_order_case\relations)
- [claims](C:\llm\KoboldCPP agentic sandbox\examples\quest_order_case\claims)
- [sentences_v0.json](C:\llm\KoboldCPP agentic sandbox\examples\quest_order_case\sentences_v0.json)
- [fragments_v0.json](C:\llm\KoboldCPP agentic sandbox\examples\quest_order_case\fragments_v0.json)
- [roles_v0.json](C:\llm\KoboldCPP agentic sandbox\examples\quest_order_case\roles_v0.json)
- [questions_v0.json](C:\llm\KoboldCPP agentic sandbox\examples\quest_order_case\questions_v0.json)
- [crosschecks_v0.json](C:\llm\KoboldCPP agentic sandbox\examples\quest_order_case\crosschecks_v0.json)
- [anomalies_v0.json](C:\llm\KoboldCPP agentic sandbox\examples\quest_order_case\anomalies_v0.json)
- [morphology_v0.json](C:\llm\KoboldCPP agentic sandbox\examples\quest_order_case\morphology_v0.json)
- [metadata_alpha_summary.md](C:\llm\KoboldCPP agentic sandbox\examples\quest_order_case\metadata_alpha_summary.md)

## Parser

Простой deterministic parser:

- [example_case_parser.py](C:\llm\KoboldCPP agentic sandbox\src\kobold_sandbox\example_case_parser.py)

План покрытия через atomic QA:

- [ATOMIC_QA_COVERAGE_PLAN.md](C:\llm\KoboldCPP agentic sandbox\ATOMIC_QA_COVERAGE_PLAN.md)

## Prompt Templates

Главная папка:

- [prompt_templates](C:\llm\KoboldCPP agentic sandbox\prompt_templates)

Особенно важно:

- relation buckets
- wrong answer probes
- morphology
- relation crosscheck

## PyneCore

В проект уже положен:

- [pynecore](C:\llm\KoboldCPP agentic sandbox\pynecore)

План интеграции:

- [PYNECORE_INTEGRATION_PLAN.md](C:\llm\KoboldCPP agentic sandbox\PYNECORE_INTEGRATION_PLAN.md)

## На чем остановились

Идея следующего шага:

- все, что сейчас было сделано вручную, постепенно заменить pipeline из atomic QA + deterministic assembly
- не просить маленькие модели собирать JSON
- просить только `yes/no` и одно слово / одно короткое значение
- source refs и token refs держать везде для provenance, text rendering и back-checking
