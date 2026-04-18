# jupyter_layer

Тонкая обёртка над Jupyter kernels с архитектурой **Panel > Object**.

Цель — использовать Jupyter как мощный execution/storage backend без того, чтобы тащить JupyterLab UI-инварианты в нашу архитектуру.

---

## Слои

```
┌─────────────────────────────────────────────┐
│  Panel (named container)                    │
│  ├── JupyterObject(id="df_raw",   [lazy])   │  L0: только IDs и списки
│  ├── JupyterObject(id="df_clean", [lazy])   │  значения — только по запросу
│  └── sub_panel("embeddings")                │
│       └── JupyterObject(id="embed_matrix")  │
└─────────────────────────────────────────────┘
         ↕  sync_from_scope()
┌─────────────────────────────────────────────┐
│  JupyterScope (L0 kernel namespace view)    │
│  list_ids()   → ["df_raw", "df_clean", …]  │  дёшево, только имена
│  fetch(name)  → Python value               │  дорого, по запросу
└─────────────────────────────────────────────┘
         ↕  ZMQ (Shell + IOPub channels)
┌─────────────────────────────────────────────┐
│  KernelSession (jupyter_client wrapper)     │
│  start() / stop() / run(code) / eval_json() │
└─────────────────────────────────────────────┘
         ↕  disk
┌─────────────────────────────────────────────┐
│  LocalStore (JSON per panel)                │
│  save/load panel meta, object meta, blobs  │
└─────────────────────────────────────────────┘
```

---

## Ключевые инварианты

| Инвариант | Почему |
|-----------|--------|
| **L0 = IDs + типы, без значений** | `list_ids()` вызывает только `globals().keys()` в ядре — дёшево, не сериализует ничего |
| **Значения — lazy** | `JupyterObject.value` кэширует при первом обращении, `invalidate()` сбрасывает |
| **Panel — scoped, не глобальный** | каждый Panel имеет своё имя + опциональный scope; нет глобального реестра |
| **Store хранит только метаданные** | значения Python-объектов остаются в ядре, в JSON кладём только id + meta |
| **Panel может быть standalone** | без `scope=` работает как чистый in-memory контейнер (полезно для конфига/метадаты) |

---

## Принятые решения (за пользователя)

1. **`jupyter_client` + ZMQ, не REST API** — прямой доступ к ядру без JupyterServer overhead. RTC (Y.js) не включён — для коллаборатива можно добавить позже, сейчас это перебор для "простенького слоя".
2. **JSON-сериализация через `eval_json()`** — fetch делает `print(json.dumps(expr))` и парсит stdout. Работает для базовых типов (int, float, str, list, dict). Для произвольных объектов — `fetch_repr()`.
3. **Локальный store = папка на диске** — формат `base_dir/<panel_name>/`. Никаких БД. Удобно для preprocessing-артефактов (chunks, embeddings, atoms).
4. **`_SKIP_PREFIXES`** в JupyterScope — фильтруем IPython-внутренности (`_`, `In`, `Out`, …), чтобы `list_ids()` не засорялся.
5. **Иерархия Panel > sub_panel()** — вложенные панели удобны для группировки (например, `preprocessing/raw`, `preprocessing/cleaned`), но сами они не ядро-бекапированы — это просто структура имён.

---

## Установка

```bash
pip install jupyter_client ipykernel
```

Сам `jupyter_layer` — часть `kobold-sandbox` (`src/jupyter_layer/`), импортируется напрямую:

```python
from jupyter_layer import KernelSession, JupyterScope, Panel, LocalStore
```

---

## Быстрый старт

```python
from jupyter_layer import KernelSession, JupyterScope, Panel, LocalStore

# 1. Запустить ядро
with KernelSession() as ks:
    scope = JupyterScope(ks)

    # 2. Выполнить препроцессинг
    scope.run("import pandas as pd; df = pd.read_csv('data.csv')")
    scope.run("df_clean = df.dropna()")

    # 3. L0: только имена, без значений
    ids = scope.list_ids()          # ['df', 'df_clean']
    typed = scope.list_typed()      # [('df', 'DataFrame'), ('df_clean', 'DataFrame')]

    # 4. Panel: контейнер с иерархией
    panel = Panel("preprocessing", scope=scope)
    panel.sync_from_scope()         # создаёт lazy JupyterObject для каждого ID

    print(panel.list_ids())         # ['df', 'df_clean']

    # 5. Материализовать только нужное
    shape = panel.get("df_clean").value  # fetch при первом обращении — repr

    # 6. Сохранить метадату
    store = LocalStore("./jl_store", "preprocessing")
    store.save_panel_meta(panel)
    store.save_blob("run_info", {"rows": 42, "source": "data.csv"})
```

---

## Структура файлов

```
src/jupyter_layer/
    __init__.py     — публичный API
    kernel.py       — KernelSession
    scope.py        — JupyterScope (L0)
    panel.py        — Panel, JupyterObject
    store.py        — LocalStore

tests/
    test_jupyter_layer.py   — happy-path (мокнутое ядро)

examples/
    jupyter_layer_example.py  — полный пример без живого ядра
```
