# Workflow v3 — Job-Based Reactive DSL (DRAFT)

## Design Philosophy

v2: "шаги выполняются последовательно, некоторые параллельно"
v3: "jobs отправляются воркерам, handlers реагируют на результаты"

Ключевой сдвиг: **не мы ждём воркера, а воркер уведомляет нас**.
Между ответами — runtime делает полезную работу.

## Layers

```
workflow/v3 YAML          ← user writes this
    ↓
Gateway Queue Runtime     ← manages jobs, subscriptions, priorities
    ↓
Assembly DSL              ← explicit steps per handler
    ↓
Workers                   ← LLM endpoints on different machines
```

## Core Concepts

### Job
```yaml
job:
  id: claims
  worker: analyzer
  payload: claims($input)
  priority: high          # high | normal | low
  timeout: 60s
  retry: 2
  tags: [extraction]
```

Job = одна LLM-задача. Ставится в очередь воркера. Runtime отслеживает статус.

### Queue
Per-worker queue с endpoint locking. Один endpoint = один active job.
```
Queue[analyzer @ 192.168.1.15:5050]:
  [ACTIVE] claims (started 2s ago)
  [PENDING] table_extract (priority: normal)
  [PENDING] style_check_1 (priority: low)

Queue[generator @ localhost:5001]:
  [ACTIVE] answer (started 5s ago)
  [PENDING] repair_1 (priority: high)
```

### Subscription (on)
```yaml
on:
  claims.done:
    do: |
      CALL @parsed, parse_sections, @claims
      CALL @entities, wrap_list, @parsed.entities, "name"
    then:
      - enqueue: table_extract

  answer.done:
    do: |
      CALL @numbered, numbered, @answer
      CALL @_, store_set, "last_answer", @answer
    then:
      - enqueue: trim_probe_1
      - enqueue: trim_probe_2
      - enqueue: trim_probe_3
      - enqueue: trim_probe_4

  all_done: [claims, answer]:
    do: |
      CALL @entities, enrich_entities, @entities, @answer
    then:
      - enqueue: verify_axioms
```

### Handler (do)
Assembly block внутри subscription. Выполняется когда job завершился.
Результат job доступен как `@{job_id}`.

### Then (chaining)
После handler: поставить новые jobs в очередь. Reactive chaining.

## Full Example: Demoness Pipeline v3

```yaml
workflow: demoness_v3
version: 3

input: >
  написать 4 описания внешности демониц...

config:
  params_int: {grammar: "...", capture: "[0-9]+", coerce: "int"}
  params_binary: {grammar: "...", capture: "[01]", coerce: "int"}

# === Phase 1: Bootstrap (parallel) ===
jobs:
  - id: claims
    worker: analyzer
    payload: claims($input)
    priority: high
    temp: 0.1
    max: 2048

  - id: answer
    worker: generator
    payload: $input
    temp: 0.7
    max: 2048

# === Reactive handlers ===
on:
  # Claims ready → parse entities
  claims.done:
    do: |
      CALL @parsed, parse_sections, @claims
      MOV @entities, @parsed.entities
      MOV @axioms, @parsed.axioms
      MOV @hypotheses, @parsed.hypotheses

  # Answer ready → prepare numbered text
  answer.done:
    do: |
      CALL @numbered_answer, numbered, @answer

  # Both ready → enrich + start entity processing
  all_done: [claims, answer]:
    do: |
      CALL @items, wrap_list, @entities, "name"
      CALL @items, enrich_entities, @items, @answer
    then:
      - for_each: items
        enqueue: trim_probe
        with: {item_idx: $index}

  # Trim probe done → slice + enqueue confirm
  trim_probe.done:
    do: |
      CALL @item.text, substr, @answer, @item.char_start, @item.char_end
    then:
      - enqueue: confirm_probe
        with: {item_idx: $item_idx}

  # Confirm probe done → enqueue style check
  confirm_probe.done:
    do: |
      MOV @item.confirmed, @confirmed
    then:
      - enqueue: style_check
        with: {item_idx: $item_idx}

  # Style check done → enqueue reaction
  style_check.done:
    do: |
      MOV @item.style_ok, @style_ok
    then:
      - enqueue: reaction_check
        with: {item_idx: $item_idx}

  # Reaction done → mark entity complete
  reaction_check.done:
    do: |
      CALL @item.status, check_status, @reaction
      MOV @item.reaction, @reaction

  # All entities done → save results
  all_done: [reaction_check.*]:
    do: |
      CALL @_, store_set, "demoness.entities", @items
      CALL @_, store_snapshot, "demoness_complete"

# === Job templates (instantiated by for_each) ===
job_templates:
  trim_probe:
    worker: generator
    mode: probe
    grammar: $config.params_int.grammar
    capture: $config.params_int.capture
    coerce: $config.params_int.coerce
    messages:
      - user: $indexed_answer    # char-indexed text
      - assistant: |
          <think>
          Блок #${item.local_id} начинается с символа ${item.char_start}
          и заканчивается на символе char_end:
    temp: 0
    max: 6

  confirm_probe:
    worker: generator
    mode: probe
    grammar: $config.params_binary.grammar
    capture: $config.params_binary.capture
    coerce: $config.params_binary.coerce
    messages:
      - user: $numbered_answer
      - assistant: |
          <think>
          Блок #${item.local_id}:
          ${item.answer}
          ((answer generated) == true) ===
    temp: 0
    max: 2

  style_check:
    worker: analyzer
    mode: probe
    grammar: $config.params_binary.grammar
    messages:
      - user: ${item.answer}
      - assistant: |
          <think>
          ((стиль аниме) == true) ===
    temp: 0
    max: 2

  reaction_check:
    worker: analyzer
    payload: |
      Evaluate this text. Reply PASS if good, FAIL + reason if not.
      ${item.answer}
    temp: 0.2
    max: 512
```

## vs v2 Comparison

| Feature | v2 | v3 |
|---|---|---|
| Execution | Sequential IP | Job queue + reactive handlers |
| Parallelism | `in_parallel` block | Implicit: different workers = parallel |
| Waiting | Blocking GEN | Subscription on job.done |
| Retry | Manual | `retry: N` on job |
| Priority | None | `priority: high/normal/low` |
| Entity loop | `for $entity in` | `for_each` → enqueue per entity |
| Error handling | Exception | `on job.failed` handler |
| Idle work | N/A | Handlers run between job completions |
| Assembly | N/A | `do:` blocks = inline Assembly |

## Runtime Scheduling

```
Time →

Worker analyzer (192.168.1.15:5050):
  ████ claims ████     ██ style_1 ██  ██ style_2 ██  ██ react_1 ██ ...

Worker generator (localhost:5001):
  ██████ answer ██████  █ trim_1 █  █ trim_2 █  █ trim_3 █  █ confirm_1 █ ...

Runtime (local CPU):
  ─── idle ───  parse  ─ idle ─  enrich  ─ idle ─  slice  ─ idle ─ ...
                 ↑                  ↑                 ↑
            claims.done      all_done         trim_probe.done
```

Workers always busy. Runtime fills gaps with transforms.

## Gateway Queue Runtime API

```python
class GatewayRuntime:
    def enqueue(self, job: GatewayJob) -> str         # returns job_id
    def subscribe(self, event: str, handler: Callable)
    def cancel(self, job_id: str) -> bool
    def status(self, job_id: str) -> JobStatus
    def drain(self) -> None                           # wait for all jobs

class GatewayJob:
    id: str
    worker: str
    payload: Any
    priority: Literal["high", "normal", "low"]
    timeout: float
    retry: int
    status: Literal["pending", "active", "done", "failed"]
    result: Any | None

class GatewayEvent:
    job_id: str
    event_type: str    # "done" | "failed" | "timeout"
    result: Any
    timestamp: float
```

## Compilation Path

```
workflow/v3 YAML
    ↓ parse
Job definitions + Subscription graph
    ↓ compile handlers
Assembly blocks (per handler)
    ↓ runtime loop
GatewayRuntime.enqueue() + .subscribe()
    ↓ execution
Workers receive HTTP, respond
    ↓ events
Subscriptions fire, handlers run Assembly
    ↓ chaining
New jobs enqueued from `then:`
```

## Open Questions

1. **State scope**: jobs share global state or isolated?
   → Proposal: shared `@data.*` namespace, job-local `@local.*`

2. **all_done wildcard**: `all_done: [reaction_check.*]` — wait for all reaction_check jobs
   → Need job naming convention: `reaction_check.entity_1`, `reaction_check.entity_2`

3. **Conditional chaining**: `then: if @status == "fail" → enqueue: repair`
   → Assembly in `do:` can set flags, `then:` checks them

4. **Streaming**: long GEN with streaming — partial results before done?
   → `on job.partial` subscription?

5. **Compatibility**: can v3 run v2 workflows?
   → Compile v2 steps → v3 sequential jobs with `then:` chaining

6. **ComfyUI / external**: non-LLM jobs (image gen, API calls)
   → Same job model, different worker type
