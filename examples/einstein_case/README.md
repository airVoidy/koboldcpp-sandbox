# Einstein Case

Живой пример для развития табличных утверждений, atomic constraints и веток гипотез.

Текущая схема:

- 5 булевых таблиц `house x value`
- прямые givens сразу заносятся в ячейки
- relational clues оформлены как `ConstraintSpec`
- для любой ячейки можно породить две git-ветки гипотез: `yes` и `no`
- первичное формализованное описание кейса лежит в `src/kobold_sandbox/cases/einstein/schema_data.py`

Следующий шаг на этом же кейсе: добавить solver-адаптер и прогон последовательных выводов.

Пример табличного рендера relation-check:

```python
from kobold_sandbox.einstein_example import render_relation_check_table

print(
    render_relation_check_table(
        "englishman-red",
        {
            "nationality_by_house": {"house-2": "englishman"},
            "color_by_house": {"house-2": "red"},
        },
        house="house-2",
    )
)
```

Пример последовательного frontier-графа:

```python
from kobold_sandbox.einstein_example import (
    build_demo_relation_frontier,
    build_first_text_frontier,
    build_relation_state_sequence_graph,
    summarize_state_graph,
)

entries, context = build_demo_relation_frontier()
graph = build_relation_state_sequence_graph(entries, context, max_depth=4)
print(summarize_state_graph(graph))

entries, context = build_first_text_frontier()
graph = build_relation_state_sequence_graph(entries, context, max_depth=7)
print(summarize_state_graph(graph))
```
