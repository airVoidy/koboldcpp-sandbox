# Prompt Templates

Минимальный стартовый набор для локальных маленьких моделей.

Идея:

- как можно больше делать без LLM
- LLM использовать только там, где реально нужен semantic judgment
- сначала резать текст на предложения
- потом строить локальные окна из `sentence[i]` и `sentence[i+1]`
- потом решать, это один логический chunk или два
- потом уже atomize / formalize каждый chunk

## Рекомендуемый пайплайн

1. `sentence_split`
2. `sentence_pair_link`
3. `chunk_merge`
4. micro-question classification:
   - `entity_question`
   - `ordering_question`
   - `choice_question`
   - `negation_question`
   - `adjacency_question`
   - `structural_question`
   - `role_binding_question`
   - `observation_vs_constraint`
   - `wrong_answer_probe`
5. `chunk_question_breakdown`
6. `atom_extraction`
7. `formalization`

## Что делать без LLM

- split по предложениям
- нормализация whitespace
- выделение enumerated lines (`1.`, `2.` ...)
- детекция явных conjunction markers
- простые шаблоны:
  - `после`
  - `до`
  - `раньше`
  - `позже`
  - `сразу после`
  - `либо ... либо ...`
  - `не`

## Где LLM полезна

- одно ли это смысловое утверждение в двух соседних предложениях
- порождает ли chunk одну или несколько гипотез
- есть ли в chunk derived interpretation или только raw statement
- как chunk лучше атомизировать при неоднозначности

## Design Rule

Для маленьких моделей лучше:

- много узких шаблонов
- мало творчества
- один prompt = один маленький decision

чем один "умный" prompt на все сразу.

## Additional Reliability Rule

Для вопросов, где точность не гарантируется, полезно хранить рядом:

- правильный короткий ответ
- неправильный короткий ответ

Это помогает:

- строить positive/negative выборки
- делать избыточные cross-check
- выделять аномалии и противоречия
