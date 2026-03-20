# Rendering Notes

Идея:

- хранить исходный текст отдельно
- хранить token index отдельно
- каждый object / relation / claim может ссылаться на:
  - token ids
  - source fragment
  - sentence id

Это позволит потом:

- рисовать graph view
- рисовать matrix/coverage view
- подсвечивать исходный текст
- делать text + infographic hybrid rendering

Полезные будущие поля:

- `source_token_refs`
- `source_char_span`
- `sentence_id`
- `fragment_id`
- `render_labels`
