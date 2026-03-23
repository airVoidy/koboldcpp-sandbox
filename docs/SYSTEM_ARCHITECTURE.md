# Reactive Task Builder — System Architecture

## Overview

Reactive Task Builder — система для оркестрации LLM-воркеров через декларативный YAML DSL.
Основана на entity-based reactive model с event-driven architecture.

**Ключевая идея**: behavior tree + functional entity system, где каждый элемент может
переопределяться через наращивание лямбд (pipeline layers).

## Stack

- **Backend**: Python 3.11+, FastAPI, uvicorn
- **Frontend**: vanilla HTML/JS (single page, no build step)
- **LLM Backend**: KoboldCPP (OpenAI-compatible `/v1/chat/completions`)
- **DSL**: YAML workflow/v2

## Модули

### 1. Workflow DSL Interpreter (`workflow_dsl.py`)

Ядро системы. Парсит и исполняет YAML workflow.

**WorkflowContext** — runtime среда:
- `$var` — ephemeral переменные (текущий run)
- `@state.path` — persistent state (node data)
- `$settings.x` — конфигурация из UI
- builtins — встроенные функции (`claims`, `table`, `numbered`, `concat`, `slice_lines`)

**Три режима LLM вызовов**:

| Mode | Описание | Use case |
|------|----------|----------|
| `prompt` | Стандартный запрос | Генерация, анализ |
| `continue` | Продолжение до EoT | Длинная генерация, continue loop |
| `probe_continue` | Inject + stop tokens, 1-10 tokens | Номер строки, true/false, короткий ответ |

**probe_continue** — transport/execution primitive, оптимизированный под KV-cache.
Model-specific (profile: `qwen_fastpath`). Почти instant на cached prefix.

**Step types**:
- Assignment: `@root.answer = $answer`
- LLM call: `analyzer -> $claims: {prompt: ...}`
- Parallel: `bootstrap: {in_parallel: [...]}`
- For loop: `for $entity in $entity_nodes: [...]`
- Parse: `parse_claims`, `parse_table`
- Verify: `verify_axioms` (accumulated think trace)
- Set: `set: {"$var": expr}`

### 2. Reactive Entity Model (`reactive_entity.py`)

Entity-based data model с event bus.

```
ReactiveTask
  ├── EventBus (listeners, propagation)
  ├── global_meta (@@namespace)
  ├── entities: OrderedDict[str, ReactiveEntity]
  ├── pipeline: [PipelineLayer] (lambda stack)
  ├── extractors: [Extractor]
  ├── constraints: [Constraint]
  └── verify_config: VerifyConfig
```

**ReactiveEntity**:
- `properties: dict[str, ReactiveProperty]` — observable fields
- `variables: dict` — ephemeral per-run
- `dialog: list[DialogEntry]` — instruction ↔ verifier conversation
- `status`: PENDING → GENERATING → EXTRACTING → DONE/FAILED

**Events**: `PropertyChangeEvent` → `EventBus.emit()` → fnmatch listeners → dispatch

**Pipeline Layers** (transparent lambda stack):
- `before_ops + inner_ops + after_ops`
- Layers wrap other layers → composable behavior
- Constraint injection: entity N+1 gets updated banned/used lists

### 3. Reactive Runner (`reactive_runner.py`)

Execution engine. Для каждой entity:
1. Build effective pipeline (base + constraint layers)
2. Flatten lambda stack → DSL ops
3. Execute via DSL interpreter
4. Run verify dialog (PASS/FAIL loop)
5. Run extractors → accumulate constraint lists
6. Post-run: evaluate cross-entity constraints

### 4. Task Parser (`reactive_task_parser.py`)

Dialog-based structure extraction. Парсит задачу через диалог с worker'ом.

**Принцип**: все промпты visible в thread, no hidden system prompts.

### 5. Universal DSL Interpreter (`dsl_interpreter.py`)

Shared interpreter для behavior tree elements и reactive runner.

**Namespaces**: `@@global`, `@node`, `$var`

**Commands**: set, copy, save, render, call, if/then/else, for_each,
append, claims, run_node, collect, halt

### 6. Behavior Orchestrator (`behavior_orchestrator.py`)

Tree/node/element data model. BehaviorTree → BehaviorNode → BehaviorElement.

## UI Architecture

### Layout
- **Left sidebar**: Workers (endpoints, roles), Settings
- **Main feed**: Recursive tree of nodes (root → entities → threads)
- **Right panel**: YAML editor + NL chat (resizable)

### Node Structure (recursive)
```
[Root Task] "написать 4 описания..."  ACTIVE
  ├── Scope tags (ENTITIES, AXIOMS — collapsible)
  ├── RESULT code block (collapsible, editable)
  ├── Thread (worker messages, pin mechanism)
  │     ├── [analyzer (claims)] ENTITIES: [...]
  │     ├── [generator (answer)] Вот 4 описания...
  │     ├── [analyzer (table)] | # | Образ | Волосы | ...
  │     └── [analyzer (verify)] ✅ Table matches...
  ├── [Entity-01] "Госпожа Теней"  DONE
  │     ├── Table tags (образ, волосы, глаза, поза)
  │     ├── RESULT (trimmed description)
  │     └── Thread (0)
  ├── [Entity-02] ...
  └── ...
```

### Pin Mechanism
- Thread message → 📌 pin → promotes to parent RESULT
- Pinned message becomes sub-node with own thread
- Recursive: any thread message can become a node

### Reactions (Slack-style)
- Emoji reactions on thread messages (✅ ❌ ⚠️ 📌)
- Multiple workers can react
- Threshold for auto-promotion

## Data Flow

```
User input
  ↓
[Parallel]
  ├── analyzer: claims extraction → ENTITIES, AXIOMS, HYPOTHESES
  └── generator: full text generation → $answer
  ↓
parse_claims → scope tags on root node
  ↓
@root.answer = $answer (RESULT code block)
  ↓
analyzer: table($answer) → markdown table
  ↓
parse_table → entity child nodes
  ↓
[For each entity]
  └── probe_continue: "last line number" → $endLineNumber (1 token!)
  └── slice_lines → $entity.answer
  ↓
verify_axioms: accumulated think trace
  ├── Table + answer in <think>
  ├── For each axiom: (({claim}) == 1) === [model answers]
  └── Summary: ✅/❌ per claim
```

## Worker Roles

| Role | Endpoint | Purpose |
|------|----------|---------|
| `generator` | local:5001 | Text generation, probe_continue trim |
| `analyzer` | remote:5050 | Claims, tables, verification |

Workers are OpenAI-compatible (`/v1/chat/completions`).
Any KoboldCPP, llama.cpp, vLLM, or OpenAI-compatible server works.

## Settings

| Setting | Default | Description |
|---------|---------|-------------|
| Temperature | 0.7 | Generation temperature |
| Max tokens | 4096 | Max generation length |
| Max continue | 20 | Continue loop limit |
| Verify max rounds | 3 | Instruction ↔ verifier dialog limit |

## Key Design Principles

1. **No hidden prompts** — all LLM calls visible in thread
2. **No hidden logs** — all output shown in UI
3. **No format filtering** — raw LLM output shown as-is
4. **Think blocks visible** — collapsible, not stripped
5. **ChatML instruct** — no system prompts, instruction in user/assistant flow
6. **Entity-based** — not node-per-task, but entity with reactive properties
7. **Lambda stacking** — behaviors composable via pipeline layers
8. **Event-driven** — listeners react on data arrival, not sequential polling
