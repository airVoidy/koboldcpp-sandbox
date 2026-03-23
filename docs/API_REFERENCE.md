# API Reference

Base URL: `http://localhost:5002`

## Workflow API

### POST /api/workflow/run

Execute a YAML workflow.

**Request:**
```json
{
  "yaml_text": "dsl: workflow/v2\nlet:\n  input: ...\nflow: [...]",
  "workers": {
    "generator": "http://localhost:5001",
    "analyzer": "http://192.168.1.15:5050"
  },
  "settings": {
    "temperature": 0.7,
    "max_tokens": 4096,
    "max_continue": 20
  },
  "input_override": "optional override for let.input"
}
```

**Response:**
```json
{
  "status": "ok",
  "thread": [
    {
      "role": "worker",
      "name": "analyzer (claims)",
      "content": "ENTITIES: [...]",
      "extra": {"tag": "claims", "think": "..."}
    }
  ],
  "vars": {"$answer": "...", "$table": "..."},
  "state": {"@root.answer": "..."},
  "entities": [
    {"_title": "Госпожа Теней", "_startNum": 3, "answer": "..."}
  ],
  "axioms": ["требуется 4 описания", "..."],
  "hypotheses": ["pos(демонша, образ1)", "..."]
}
```

### GET /api/workflow/default

Get default workflow YAML template.

**Response:** YAML text (content-type: text/plain)

### GET /api/workflow/spec

Get Workflow DSL specification.

**Response:** Markdown text

---

## Think Lab API

Full runtime/UI specification: `docs/THINK_LAB_SPEC.md`

### GET /think-lab

Open the dedicated Think Lab research page.

Use case:
- clean-context `<think>` experiments
- stop-token breakpoints
- assistant-prefill continuation
- JS-side replacement and derived values

### POST /api/think-lab/step

Proxy one raw OpenAI-compatible completion step to an external worker.

**Request:**
```json
{
  "url": "http://127.0.0.1:5001",
  "payload": {
    "messages": [
      {"role": "user", "content": "numbered text"},
      {"role": "assistant", "content": "<think>prefix..."}
    ],
    "temperature": 0,
    "max_tokens": 6,
    "stop": ["\n", "\""],
    "continue_assistant_turn": true,
    "cache_prompt": false
  }
}
```

**Response:**
```json
{
  "status": "ok",
  "content": "17",
  "finish_reason": "stop",
  "latency_ms": 42,
  "raw": {
    "choices": [
      {
        "message": {"content": "17"},
        "finish_reason": "stop"
      }
    ]
  }
}
```

Validation errors:
- `400 url is required`
- `400 payload must be an object`

Transport/worker failures:
- `502` with upstream error text when available

---

## Reactive Task API

### POST /api/reactive/task

Create task from dialog state.

**Request:**
```json
{
  "dialog_state": {
    "message": "написать 4 описания...",
    "turns": [...]
  }
}
```

### GET /api/reactive/task

Get current task state.

**Response:**
```json
{
  "task_id": "task-001",
  "entities": {
    "entity-01": {
      "status": "DONE",
      "properties": {
        "text": {"value": "Демонша с чёрными волосами..."},
        "hair_color": {"value": "чёрный"}
      }
    }
  },
  "global_meta": {
    "used_hair_colors": ["чёрный", "серебристый"]
  },
  "pipeline": [...],
  "extractors": [...],
  "constraints": [...]
}
```

### POST /api/reactive/task/run

Execute full pipeline for all entities.

### POST /api/reactive/task/entity/{entity_id}

Update entity property.

**Request:**
```json
{
  "property": "text",
  "value": "Updated description..."
}
```

### POST /api/reactive/task/pipeline/add

Add pipeline layer.

**Request:**
```json
{
  "layer": {
    "layer_id": "style-enforce",
    "ops": [{"set": {"style": "gothic"}}],
    "wraps": "base-generation"
  }
}
```

### GET /api/reactive/task/events

Get event log.

**Response:**
```json
{
  "events": [
    {
      "event_key": "entity-01.text.changed",
      "entity_id": "entity-01",
      "property_name": "text",
      "old_value": null,
      "new_value": "..."
    }
  ]
}
```

### GET /api/reactive/task/status

Get task execution status.

### POST /api/reactive/chat/send

Send message in dialog (triggers worker calls).

**Request:**
```json
{
  "message": "написать 4 описания...",
  "workers": {
    "generator": "http://localhost:5001",
    "analyzer": "http://192.168.1.15:5050"
  },
  "settings": {"temperature": 0.7},
  "workflow_yaml": "dsl: workflow/v2\n..."
}
```

### POST /api/reactive/chat/next-entity

Create next entity in sequence.

---

## Behavior Tree API

### GET /api/behavior/tree

Get current behavior tree.

### POST /api/behavior/tree

Create/replace behavior tree.

### GET /api/behavior/nodes/{node_id}

Get node details.

### POST /api/behavior/nodes/{node_id}

Update node.

### POST /api/behavior/run

Run full tree.

### POST /api/behavior/nodes/{node_id}/run

Run single node.

### GET /api/behavior/status

Get execution status.

### POST /api/behavior/agents

Register LLM agent endpoint.

**Request:**
```json
{
  "name": "main",
  "url": "http://localhost:5001"
}
```

### GET /api/behavior/agents

List registered agents.

---

## Logic API

### POST /api/logic/parse

Parse text into atomic claims.

**Request:**
```json
{
  "task_text": "Норвежец живёт в первом доме...",
  "answer_text": "Англичанин живёт в красном доме"
}
```

### POST /api/logic/verify

Verify claims against task.

**Request:**
```json
{
  "task_text": "...",
  "answer_text": "...",
  "url": "http://192.168.1.15:5050"
}
```

**Response:**
```json
{
  "entities": ["англичанин", "норвежец"],
  "axioms": ["pos(норвежец) == 0"],
  "hypotheses": ["pos(англичанин) == pos(красный)"],
  "axiom_count": 15,
  "stable_worlds": 1
}
```

### POST /api/logic/parse-structured

Parse into structured table.

---

## LLM Worker API (KoboldCPP compatible)

Workers expose OpenAI-compatible endpoint:

### POST /v1/chat/completions

**Request:**
```json
{
  "messages": [
    {"role": "user", "content": "..."},
    {"role": "assistant", "content": "<think>\n..."}
  ],
  "temperature": 0.1,
  "max_tokens": 10,
  "stop": ["\n", " "],
  "stream": false,
  "cache_prompt": false,
  "continue_assistant_turn": true
}
```

**Response:**
```json
{
  "choices": [{
    "message": {"role": "assistant", "content": "42"},
    "finish_reason": "stop"
  }]
}
```

**Key parameters:**
- `continue_assistant_turn: true` — continue from last assistant message
- `stop: [...]` — stop tokens (for probe_continue)
- `cache_prompt: false` — disable prompt caching (for continue mode)
- `stream: false` — non-streaming response

---

## UI Pages

| URL | Description |
|-----|-------------|
| `/reactive-chat` | Reactive Task Builder UI |
| `/behavior` | Behavior Tree Editor UI |
| `/` | Main chat UI |

---

## External Integration Points

### Adding a New Worker

1. Start any OpenAI-compatible server:
   ```bash
   # KoboldCPP
   koboldcpp --model model.gguf --port 5001

   # llama.cpp
   llama-server -m model.gguf --port 5001

   # vLLM
   vllm serve model --port 5001
   ```

2. Register in UI: Workers section → add URL + assign role

3. Or via API:
   ```bash
   curl -X POST http://localhost:5002/api/behavior/agents \
     -H "Content-Type: application/json" \
     -d '{"name": "my-worker", "url": "http://localhost:5001"}'
   ```

### Adding Custom Builtins

Pass `builtins` dict to `run_workflow()`:
```python
from kobold_sandbox.workflow_dsl import run_workflow

ctx = run_workflow(
    yaml_text=yaml_str,
    workers={"generator": "http://localhost:5001"},
    builtins={
        "my_func": lambda x: x.upper(),
        "extract_names": lambda text: re.findall(r'"([^"]+)"', text),
    }
)
```

### Adding Custom Pipeline Layers

```python
from kobold_sandbox.reactive_entity import PipelineLayer

layer = PipelineLayer(
    layer_id="my-constraint",
    before_ops=[{"set": {"banned_colors": "@@used_colors"}}],
    wraps="base-generation",
    after_ops=[{"call": {"fn": "validate_unique"}}],
    tags=["constraint", "uniqueness"]
)
task.pipeline.append(layer)
```

### WebSocket Events (future)

Currently polling-based. Future: WebSocket at `/ws/workflow` for real-time updates.

### Embedding in External App

```html
<iframe src="http://localhost:5002/reactive-chat" width="100%" height="800px"></iframe>
```

Or use API directly — all endpoints are stateless REST.
