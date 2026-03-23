# External Module Integration Guide

Этот документ описывает как подключить внешний модуль к Reactive Task Builder.

## Контракт

Внешний модуль взаимодействует с системой через:

1. **REST API** (`/api/workflow/run`, `/api/reactive/*`)
2. **YAML DSL** (workflow definition)
3. **Worker endpoints** (OpenAI-compatible LLM servers)
4. **Builtins** (Python functions, регистрируемые в runtime)

## Сценарии интеграции

### A. Внешний модуль как Worker

Модуль выступает как LLM endpoint. Должен реализовать:

```
POST /v1/chat/completions
```

С поддержкой:
- `messages` (chat format)
- `temperature`, `max_tokens`
- `stop` (stop sequences)
- `continue_assistant_turn` (для probe_continue)
- `stream: false` (non-streaming)

**Response format:**
```json
{
  "choices": [{
    "message": {"role": "assistant", "content": "..."},
    "finish_reason": "stop" | "length"
  }]
}
```

**Пример**: прокси-модуль, который берёт запрос, добавляет свою логику, и перенаправляет на LLM.

### B. Внешний модуль как Orchestrator

Модуль вызывает `/api/workflow/run` с YAML workflow и получает результаты.

```python
import requests

workflow = """
dsl: workflow/v2
let:
  input: "моя задача"
flow:
  - generator -> $answer:
      prompt: $input
      temperature: 0.7
      max_tokens: 2048
"""

resp = requests.post("http://localhost:5002/api/workflow/run", json={
    "yaml_text": workflow,
    "workers": {
        "generator": "http://localhost:5001",
        "analyzer": "http://192.168.1.15:5050"
    },
    "settings": {"temperature": 0.7, "max_tokens": 4096}
})

result = resp.json()
print(result["vars"]["$answer"])
print(result["thread"])  # all LLM calls visible
```

### C. Внешний модуль как Builtin Function

Регистрация custom функции, доступной из YAML DSL:

```python
from kobold_sandbox.workflow_dsl import run_workflow

def my_validator(text):
    """Custom validation logic."""
    issues = []
    if len(text) < 100:
        issues.append("too short")
    if "демонша" not in text.lower():
        issues.append("missing character")
    return {"pass": len(issues) == 0, "issues": issues}

ctx = run_workflow(
    yaml_text=yaml_str,
    workers={...},
    builtins={"validate": my_validator}
)
```

Использование в YAML:
```yaml
- set:
    "$result": validate($entity.answer)
```

### D. Внешний модуль как Post-processor

Слушает результаты workflow и обрабатывает:

```python
resp = requests.post("http://localhost:5002/api/workflow/run", json={...})
result = resp.json()

# Получаем все entities с answers
for entity in result.get("entities", []):
    title = entity.get("_title")
    answer = entity.get("answer", "")

    # Внешняя обработка
    processed = my_module.process(answer)

    # Записываем обратно
    requests.post(
        f"http://localhost:5002/api/reactive/task/entity/{entity['_id']}",
        json={"property": "processed_text", "value": processed}
    )
```

## Структура данных

### Thread Message

```python
{
    "role": "worker" | "user" | "system",
    "name": "analyzer (claims)" | "generator (answer)" | ...,
    "content": "текст сообщения",
    "extra": {
        "tag": "claims" | "table" | "verify" | "trim" | "check",
        "think": "содержимое <think> блока (если есть)"
    }
}
```

### Entity Node (из parse_table)

```python
{
    "_title": "Госпожа Теней",
    "_startNum": 3,           # номер первой строки в answer
    "_firstLine": "Образ 1...", # текст первой строки
    "_row": {                  # raw table row
        "Образ": "Госпожа Теней",
        "Волосы": "чёрные",
        "Глаза": "алые"
    },
    "answer": "Trimmed description text..."  # заполняется после trim
}
```

### Workflow Context Variables

```python
ctx.vars = {
    "$input": "задача пользователя",
    "$claims": "ENTITIES: [...]\nAXIOMS: [...]",
    "$answer": "полный текст генерации",
    "$table": "markdown table",
    "$entity_nodes": [entity_node, ...],
    "$entities": ["демонша", "образ1", ...],
    "$axioms": ["требуется 4 описания", ...],
    "$hypotheses": ["pos(демонша, образ1)", ...],
}
```

## Probe Continue — Model-Specific Protocol

Для внешних модулей, которые хотят использовать probe_continue:

```python
import requests

# 1. Send initial context
messages = [
    {"role": "user", "content": numbered_text},
    {"role": "assistant", "content": '<think>\nОписание "Госпожа Теней" заканчивается на строке "'}
]

# 2. Probe with stop tokens
resp = requests.post("http://localhost:5001/v1/chat/completions", json={
    "messages": messages,
    "continue_assistant_turn": True,
    "temperature": 0.1,
    "max_tokens": 10,
    "stop": ["\n", "\"", " "],
    "stream": False,
    "cache_prompt": False
})

end_line = resp.json()["choices"][0]["message"]["content"].strip()
# "42" — один токен, instant на KV cache
```

**Требования к LLM серверу:**
- Поддержка `continue_assistant_turn`
- Поддержка `stop` sequences
- KV cache (иначе нет speed benefit)
- Stable think-prefix continuation

**Совместимые серверы:**
- KoboldCPP ✅
- llama.cpp server ✅ (с `--cont-batching`)
- vLLM ✅
- OpenAI API ❌ (нет `continue_assistant_turn`)

## File Structure

```
docs/
  SYSTEM_ARCHITECTURE.md    ← вы здесь (соседний файл)
  API_REFERENCE.md          ← полный API reference
  EXTERNAL_MODULE_GUIDE.md  ← этот файл

examples/behavior_case/
  WORKFLOW_DSL_SPEC.md      ← спецификация DSL
  demo_workflow.yaml        ← canonical workflow example

src/kobold_sandbox/
  workflow_dsl.py           ← DSL interpreter (entry point: run_workflow)
  reactive_entity.py        ← Entity model, EventBus, Pipeline
  reactive_runner.py        ← Execution engine
  reactive_task_parser.py   ← Dialog parser
  dsl_interpreter.py        ← Universal DSL interpreter
  behavior_orchestrator.py  ← Tree/node model
  server.py                 ← FastAPI routes

tools/
  reactive_chat.html        ← UI

tests/
  test_workflow_dsl.py      ← Workflow tests
  test_reactive_entity.py   ← Entity tests
```
