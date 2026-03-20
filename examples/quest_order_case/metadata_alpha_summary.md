# Metadata Alpha Summary

Что уже выжато из базового вопроса за первый проход:

- `answer_frame.json`
- `raw_claims.json`
- `atoms_v0.json`
- `relation_buckets_v0.md`
- `objects/`
- `relations/`
- `claims/`
- `source_text.md`
- `source_tokens_v0.json`
- `sentences_v0.json`
- `fragments_v0.json`
- `roles_v0.json`
- `questions_v0.json`
- `crosschecks_v0.json`
- `anomalies_v0.json`

## Что это дает

- provenance до уровня token refs
- разбиение на sentences и fragments
- первый object graph
- role inventory
- positive/negative micro-questions
- relation crosschecks
- anomaly logging

## Что еще можно выжать в этом проходе

- morphology по всем surface forms
- char spans
- sentence-to-token exact mapping
- direct/derived split по каждому atom
- unresolved tail inventory
- первые grouped-hypothesis seeds
