# Kobold Sandbox

Локальный sandbox для `koboldcpp`, где каждая гипотеза живет в отдельном узле графа:

- у узла есть папка `nodes/<node>/workspace`
- состояние узла хранится в заметках и таблицах
- ветвление реализовано через `git branch` + `git worktree`
- модель запускается на контексте конкретного узла, а результаты складываются в `nodes/<node>/runs`

## Зачем это

Такой формат удобен для задач с итеративным рассуждением:

- логические головоломки типа задачи Эйнштейна
- исследование нескольких конкурирующих гипотез
- агентные прогоны, где надо хранить промежуточные выводы отдельно
- анализ файлов с разными ветками интерпретации

## Быстрый старт

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -e .
kobold-sandbox init --kobold-url http://192.168.1.15:5050 --model qwen3.5-9b
```

Создать ветку гипотезы:

```bash
kobold-sandbox branch "red-house-hypothesis" --parent-id root --tag einstein
```

Записать таблицу:

```bash
kobold-sandbox table red-house-hypothesis --name clues.csv --content "house,color,owner`n1,red,?`n2,blue,?"
```

Прогнать модель на узле:

```bash
kobold-sandbox models
kobold-sandbox run "Проверь гипотезу и выпиши противоречия" --node-id red-house-hypothesis --model "точный-id-из-models"
```

Поднять локальный API:

```bash
kobold-sandbox serve --host 127.0.0.1 --port 8060
```

## MCP-like Interface

Поверх основного API есть MCP-like JSON-RPC endpoint:

```text
http://127.0.0.1:8060/api/mcp
```

Есть и `stdio`-режим для host-клиентов:

```bash
kobold-sandbox mcp-stdio
```

Для агентных клиентов см.:

- `MCP_AGENTS.md`
- `examples/mcp_host_demo.py`
- `examples/mcp_host_demo.ps1`

## Структура

```text
.sandbox/
  state.json
  repo/
nodes/
  root/
    notes.md
    tables/
    runs/
    workspace/
  red-house-hypothesis/
    notes.md
    tables/
    runs/
    workspace/
```

## Идея развития

Следующий логичный шаг: поверх `/graph` и `/nodes/{id}/run` добавить UI в виде mind map, где:

- ребра соответствуют `parent_id`
- выбор узла показывает файлы, заметки и таблицы
- новая гипотеза создает новую git-ветку и worktree
- сравнение веток можно делать через `git diff` и сводные таблицы
