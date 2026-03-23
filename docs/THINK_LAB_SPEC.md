# Think Lab Specification

## Overview

Think Lab is a dedicated stateless research page for studying:

- `<think>` verification flows
- Qwen-style continuation shortcuts
- stop-token breakpoints inside assistant-prefill
- JS-side replacement and derived values between continuation steps

The page is intentionally separate from chat. Each run starts from a clean context and is driven by an explicit assistant tape assembled from:

- base messages
- assistant prefill / prebuilt think
- breakpoint slots
- locally computed replacements

Route:

- `GET /think-lab`

Step API:

- `POST /api/think-lab/step`

## Goals

- Provide a fast lab for probing exact continuation behavior at a specific place in assistant output.
- Let the user pause generation on unique stop conditions and substitute a computed value before the next continuation.
- Keep transport simple and stateless: one request per step, full trace visible.
- Support Qwen experimentation without forcing one prompt format or one chat mode.

## Non-Goals

- Persistent chat history
- hidden orchestration
- generic workflow execution
- server-side expression runtime

Think Lab is a narrow research surface, not a replacement for `workflow_dsl` or `reactive-chat`.

## High-Level Architecture

### Backend

Backend exposes a single stateless proxy step:

- receives worker `url`
- receives raw OpenAI-compatible payload
- forwards to `POST {url}/v1/chat/completions`
- returns:
  - extracted `content`
  - `finish_reason`
  - `latency_ms`
  - full `raw` response

This keeps Think Lab independent from typed request models and allows experimental payload fields such as:

- `continue_assistant_turn`
- `stop`
- `cache_prompt`
- model-specific extras in the future

The proxy should also extract and forward token usage from the worker response when available:

- `prompt_tokens`
- `completion_tokens`
- `tokens_per_second` (if reported by KoboldCpp)

These metrics are critical for verifying KV cache behavior (see KV Cache Strategy below).

### Frontend

Frontend is a standalone vanilla HTML/JS page with three concerns:

1. Editor/state layer
   - transport settings
   - fixtures JSON
   - base messages
   - assistant prefill template

2. Runtime layer
   - parses assistant template into literal segments and slots
   - builds current assistant prefix
   - executes one slot at a time
   - stores slot results in local runtime state

3. Inspection layer
   - live assistant preview
   - per-slot controls
   - vars panel
   - raw trace per step

## KV Cache Strategy

The main performance advantage of probe_continue is KV cache reuse. Each continuation step shares the prefix with the previous one, so generation is near-instant when the cache hits.

Recommended `cache_prompt` usage:

- **Step 1** (first probe in a run): `cache_prompt` can be false — this is the cold start that seeds the cache.
- **Step 2+** (subsequent probes): `cache_prompt: true` — the worker reuses the KV cache from the shared prefix. Only the new suffix (replacement text + next literal segment) needs processing.

How to verify the cache is working:

- `prompt_tokens` should be 0 or very small on step 2+ (only the delta is processed).
- `latency_ms` should drop dramatically (e.g. 500ms → 30ms).
- `tokens_per_second` should spike because generation is the only cost.

The UI should surface these metrics per-step in the trace panel so the user can confirm cache behavior at a glance.

Note: `cache_prompt` is KoboldCpp-specific. Other backends (vLLM, llama.cpp) may handle prefix caching automatically or via different flags. The spec does not mandate cache behavior — it only mandates that the metrics are visible so the user can verify.

## Runtime Model

Think Lab runtime is client-side and ephemeral.

Core state:

- `segments`: literal or slot parts of assistant template
- `slotOrder`: execution order of slots
- `slotConfigs`: per-slot config from UI
- `slotResults`: committed outputs/replacements
- `cursor`: current slot index
- `pausedAt`: last completed slot
- `trace`: chronological step log

The assistant output is not generated as one streaming run. It is reconstructed as:

1. take base messages
2. append assistant prefix made of:
   - literal text already present in template
   - replacements already committed for previous slots
3. execute current slot
4. commit replacement
5. continue with next slot

## Template Format

Assistant template may contain literal text and slot markers:

```text
[[probe:endLine]]
[[calc:entityBlock]]
[[manual:overrideValue]]
```

If `Wrap in <think>` is enabled, the entire editor content becomes:

```text
<think>
...template body...
</think>
```

## Slot Types

### `probe`

`probe` performs one remote continuation step.

Per-slot fields:

- `stopText`
- `maxTokens`
- `transform`
- `replacement`
- `autoContinue`

Execution:

1. build payload from base messages + assistant prefix
2. set `continue_assistant_turn` if enabled
3. send request to `/api/think-lab/step`
4. receive raw text capture
5. detect which stop token triggered (see Stop Token Detection)
6. evaluate `transform` (with `capture`, `matchedStop` in scope)
7. evaluate optional `replacement`
8. commit result

#### Stop Token Detection

KoboldCpp returns `finish_reason: "stop"` but does not report which stop token matched. The runtime detects it heuristically:

1. If `finish_reason` is `"stop"`, check `capture` trailing bytes against each configured stop token.
2. The first match (longest-first priority) is recorded as `matchedStop`.
3. If no match is found, `matchedStop` is `null` (model may have consumed the stop token).

`matchedStop` is available in transform/replacement scope and shown in the slot result card.

#### Finish Reason Handling

The `finish_reason` value determines the slot result status:

- `"stop"` — normal: a breakpoint stop token triggered. Shown as green chip.
- `"length"` — model hit `max_tokens` before any stop token. Shown as yellow chip `max_tokens reached`. This usually means the stop token pattern was wrong or the model diverged.
- EOS / `"stop"` without matched stop token — model ended naturally (e.g. `</think>` or EoT). Shown as orange chip `model stopped (no breakpoint match)`. This is a signal that the prefill template does not match model expectations.

The UI should make these visually distinct so the user immediately sees whether the breakpoint worked as intended.

### `calc`

`calc` is fully local and does not call the model.

Per-slot fields:

- `expr`
- `replacement`
- `autoContinue`

Execution:

1. evaluate `expr` in JS runtime
2. if `replacement` is present, evaluate it using `value`
3. commit result

### `manual`

`manual` also stays local.

Per-slot fields:

- `replacement`
- `autoContinue`

Execution:

1. take replacement from UI
2. commit result directly

## Expression Model

Expressions are evaluated in JS on the client.

Supported styles:

- JS expression prefixed with `=`
- mini-expression style for simple helper calls
- template interpolation via `{$path}`

Examples:

```text
=H.int(capture, capture)
=H.sliceLines(answer, entity._startNum, vars.endLine)
$entity._title
numbered($answer)
Description "{$entity._title}" starts here
```

### Runtime Scope

Each evaluation sees:

- fixture inputs as top-level names
- `inputs`
- `vars`
- `captures`
- `results`
- `last`
- helper namespace `H`

### Built-in Helpers

Current helper set:

- `H.trim(value)`
- `H.int(value, fallback)`
- `H.lines(value)`
- `H.numbered(value)`
- `H.sliceLines(value, start, end)`
- `H.json(value)`
- `H.concat(...parts)`

## Message Input

Base messages accept either:

- JSON array
- YAML-lite `messages:` block

Example:

```yaml
messages:
- user: numbered($answer)
```

or:

```json
[
  {"role": "user", "content": "numbered($answer)"}
]
```

At runtime, each message content is resolved through the same expression/template layer before request assembly.

All three roles are supported: `system`, `user`, `assistant`. Multi-turn sequences are allowed:

```yaml
messages:
- system: You are a structured reasoning assistant.
- user: numbered($answer)
- assistant: I see the text has {$lineCount} lines.
- user: Now find where "{$entity._title}" starts.
```

This is useful for Qwen instruct mode where a system message affects behavior, or for multi-turn context experiments.

## ChatML / Instruct Mode

Think Lab supports two prompt assembly modes via the preset selector:

### Chat mode (default)

Messages are sent as-is in OpenAI `messages` format. The worker (KoboldCpp) handles ChatML wrapping internally. This is the simplest mode and works for most experiments.

### Instruct mode (ChatML manual)

For Qwen instruct experiments, the user may need to control ChatML tokens directly. In instruct mode, messages are assembled into a single raw prompt:

```
<|im_start|>system
You are a helpful assistant.<|im_end|>
<|im_start|>user
numbered text here<|im_end|>
<|im_start|>assistant
<think>
...prefill template...
```

Note: the assistant turn is deliberately left open (no `<|im_end|>`) so the model continues from the prefill.

The preset selector only changes the seed content in the editors. The actual request is always built from whatever is visible on the page. This means the user can manually construct any prompt format — ChatML, Alpaca, raw, etc. — by editing the messages and template directly.

Model-specific tokens like `<|im_start|>`, `<|im_end|>`, `<|endoftext|>` can also be used as stop tokens in breakpoints when needed.

## Raw Request Preview

Before sending a probe step, the user can inspect the exact assembled payload via a "Preview Request" toggle in the Runtime panel. This shows:

- the full `messages` array with all expressions resolved
- the assistant content (prefix + all committed replacements up to current slot)
- all request parameters (temperature, max_tokens, stop, etc.)

This is essential for debugging ChatML formatting, verifying that template interpolation produced the expected text, and catching off-by-one issues in the prefill.

The preview updates live as the user edits the template or fixtures — no need to click Run first.

## Keyboard Shortcuts

For fast iteration:

- `Ctrl+Enter` — Run Fresh (reset + execute until first pause)
- `Shift+Enter` — Continue (execute next slot)
- `Ctrl+Shift+Enter` — Run All (execute all slots without pausing)
- `Ctrl+R` — Retry Last Slot
- `Ctrl+P` — Toggle Raw Request Preview

Shortcuts are active when focus is inside the Think Lab page. They do not interfere with normal text editing in textareas (the shortcut only fires when the textarea is not focused, or via a dedicated modifier).

## UI Layout

### Left Column

- worker URL
- model
- preset selector
- temperature
- default max tokens
- default stop tokens
- `cache_prompt`
- `continue_assistant_turn`
- fixtures JSON

### Center Column

- base messages editor
- assistant prefill / think template editor
- runtime controls:
  - `Run Fresh`
  - `Continue`
  - `Run All`
  - `Retry Last Slot`
- status chips
- error box
- assistant preview
- full trace

### Right Column

- parsed slot cards
- per-slot parameters
- slot result preview (with finish_reason chip + matchedStop indicator)
- per-slot token metrics (prompt_tokens, completion_tokens, latency_ms, tok/s)
- slot attempt history (previous results preserved on retry)
- vars panel

## API Contract

### `POST /api/think-lab/step`

Request:

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

Response:

```json
{
  "status": "ok",
  "content": "17",
  "finish_reason": "stop",
  "latency_ms": 42,
  "prompt_tokens": 0,
  "completion_tokens": 2,
  "tokens_per_second": 47.6,
  "raw": {"choices": [...], "usage": {...}}
}
```

Token metrics are extracted from the worker `usage` object when present. `tokens_per_second` is computed as `completion_tokens / (latency_ms / 1000)` if not reported directly. Missing fields are returned as `null`.

Validation errors:

- `400 url is required`
- `400 payload must be an object`

Remote worker failures are surfaced as `502`.

## Canonical Example

```yaml
messages:
- user: numbered($answer)
```

Assistant template:

```text
Split the text into numbered blocks.
Description "{$entity._title}" starts at line "{$entity._startNum}" "{$entity._firstLine}"
and ends at line "
[[probe:endLine]]
"
Now I can recover the full block:
[[calc:entityBlock]]
```

Slot config:

- `endLine.stopText = ["\n", "\""]`
- `endLine.maxTokens = 6`
- `endLine.transform = =H.int(capture, capture)`
- `entityBlock.expr = =H.sliceLines(answer, entity._startNum, vars.endLine)`

This pattern is the main target: pause at a tiny local value, then derive a larger structured value from already known context.

## Implemented MVP

Current implementation supports:

- dedicated `/think-lab` page
- stateless step proxy
- `probe`, `calc`, `manual` slots
- clean-context runs
- assistant preview with committed replacements
- per-slot controls and rewind
- trace of request/response/output
- example scenario preloaded in UI

## Error Recovery

When a probe step fails (network error, worker 500, timeout), the pipeline stops at the failed slot:

- The error is shown in the error box with the slot id and HTTP status.
- The cursor stays at the failed slot — the user can fix config (URL, stop tokens, etc.) and hit Retry.
- All previously committed slot results are preserved. No need to re-run the entire pipeline.
- If the user hits Run Fresh, everything resets as expected.

Partial failure on slot 3 of 5 means slots 1-2 are committed, slot 3 shows the error, slots 4-5 are untouched. This is the natural behavior of the cursor model.

## Fork and Compare

For research, the user often needs to try the same breakpoint with different injections and compare outputs.

### Slot attempt history

When a slot is retried (via Rewind or Retry), the previous result is not discarded but pushed to an `attempts` array on the slot result. The UI shows the latest attempt as the active result, with a collapsible "Previous attempts" section listing older results with their timestamps and values.

This lets the user compare outputs without manually copying them.

### Fork from here (future)

A planned extension: "Fork" button on any slot that clones the entire pipeline state up to that point into a new tab/panel. The user can then modify the injection in the fork and run both paths independently, comparing side-by-side.

## Export

### Export as JSON scenario

The entire Think Lab state (fixtures, messages, template, slot configs) can be exported as a single JSON file and re-imported later. This enables sharing experiments and building a library of known-good patterns.

Export format:

```json
{
  "format": "think-lab/v1",
  "transport": {"url": "...", "temperature": 0, "maxTokens": 16, "cachePrompt": false, "continueAssistantTurn": true},
  "fixtures": {...},
  "messages": "messages:\n- user: numbered($answer)",
  "template": "...",
  "wrapThink": true,
  "slotConfigs": {"endLine": {...}, "entityBlock": {...}}
}
```

### Export as workflow/v2 snippet

Since Think Lab's goal is to discover patterns for `workflow_dsl`, a "Copy as DSL" button generates a workflow/v2 YAML snippet from the current pipeline:

```yaml
- generator -> $endLine:
    mode: probe_continue
    messages:
      - user: numbered($answer)
      - assistant: |
          <think>
          Description "{$entity._title}" starts at line "{$entity._startNum}"
          and ends at line "
    stop: ["\n", "\""]
    max_tokens: 6
    temperature: 0
- set:
    "$entity.answer": slice_lines($answer, $entity._startNum, $endLine)
```

This bridges the gap between research (Think Lab) and production (workflow_dsl).

## Watch Mode (future)

Run the same experiment N times and collect statistics:

- average / p50 / p99 latency per slot
- output variance (how often the model produces the same value)
- finish_reason distribution (what % hit the breakpoint vs length vs EOS)

Useful for evaluating probe stability: if the model returns different values on identical input, the pattern is fragile and needs redesign.

## Expected Extensions

Natural next steps beyond what is already specified above:

- user-defined helper registry (custom `H.*` functions)
- richer stop-token UX: chip/tag input with visual special characters (`[↵]` `["]` `[⎵]`) instead of escaped text
- optional streaming step mode (for longer generations, with early abort)
- branching or conditional local slots (if/else based on probe result)
- server-side safe expression runtime if JS becomes too loose

## Position in the System

Think Lab should remain a narrow tool beside existing modules:

- `workflow_dsl` stays the execution DSL
- `reactive-chat` stays the orchestration/chat surface
- Think Lab stays the breakpoint-level microscope for assistant-prefill continuation research
