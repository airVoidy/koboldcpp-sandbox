# Worker Output Format

Формат для возврата результата шага first-layer LLM worker.

## Goal

После каждого saturating шага вернуть:

- машинно-удобный outcome
- llm-friendly текст
- Python-блок с ключевыми переменными/выводами

Это полезно даже если новых фиксированных ячеек нет, но появились новые ограничения или сужения доменов.

## Recommended Shape

```text
```python
outcome_id = '...'
branch_status = 'saturated'
affected_cells = [...]
consequences = [...]
```

Result:
- root_hypothesis: ...
- checked: ...
- affected: ...
- cells: ...
- consequences: ...

Hypotheses:
| hypothesis_id | checked | affected |
| --- | --- | --- |
| ... | yes | yes/no |

- effects:
  - effect-id: N transformation(s)
```

## Why This Works Well For LLMs

- Python-блок хорошо читается и легко копируется в следующий шаг
- summary ниже дает краткий человеческий контекст
- можно вернуть шаг даже без новых fixed cells
- можно сообщать новые derived constraints и domain narrowings

## Storage

- `analysis/outcome.json`
- `analysis/effects/*.json`
- `analysis/step-xxxx.json`

Текстовый рендер можно:

- сохранять в `analysis/worker_output.md`
- или сразу отдавать воркеру/API/UI
