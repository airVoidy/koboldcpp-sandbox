# Workflow DSL Spec

## Purpose

This DSL describes LLM-driven orchestration in a compact YAML form.

It is intended for workers that:

- receive a natural-language task
- build an execution workflow
- call generator/analyzer workers
- parse intermediate artifacts
- distribute outputs into entities
- expose manual triggers such as verify/check

The DSL is declarative.
It is not Python code.

## Top-Level Shape

```yaml
dsl: workflow/v2
let: {}
flow: []
triggers: {}
```

## Names

- `$x` runtime variable
- `$obj.field` nested runtime field
- `@x` persistent state path
- `@root.answer` persistent nested path
- `{$expr}` interpolation inside strings

## Core Sections

### `let`

Named initial variables.

Example:

```yaml
let:
  input: "написать 4 описания внешности демонши"
```

### `flow`

Ordered main execution steps.

Example:

```yaml
flow:
  - step 1
  - step 2
```

### `triggers`

Named manual or conditional workflows.

Example:

```yaml
triggers:
  verify:
    - step
  check:
    - step
```

## Step Forms

### 1. Assignment

```yaml
- @root.answer = $answer
- $entity.answer = slice_lines($answer, $start, $end)
```

Meaning:

- evaluate right side
- assign to left side

### 2. LLM Call

```yaml
- analyzer -> $claims:
    prompt: claims($input)
    temperature: 0.1
    max_tokens: 2048
```

Fields:

- worker name on the left
- output target after `->`
- config in mapping body

Supported config keys:

- `prompt`
- `continue`
- `temperature`
- `max_tokens`
- `stop`
- `grammar` — GBNF grammar constraint (e.g. `"[0-9]+"`, `"[01]"`)
- `tag`

### 3. Continue Call

```yaml
- generator -> $result:
    continue:
      - user: $input
      - assistant: |
          <think>
          reasoning here
    temperature: 0.6
    max_tokens: 2048
```

Use `continue` when the worker must continue an existing assistant turn until EoT.

### 4. Probe Continue

```yaml
- generator -> $end_line:
    mode: probe_continue
    messages:
      - user: numbered($answer)
      - assistant: |
          <think>
          Описание "{$entity.title}" начинается со строки
          под номером "{$entity.startNum}" "{$entity.firstLineText}"
          и длится до строки под номером "line number:
    stop: ["\n", "\"", " "]
    max_tokens: 10
    temperature: 0.1
```

Use `mode: probe_continue` to inject into think and get a short answer (1-10 tokens).

Difference from `continue`:

- `continue` runs until EoT (full generation)
- `probe_continue` injects + stops at `stop` tokens (probe, read one answer)

Both use `continue_assistant_turn: true` under the hood.

Common message keys:

- `user: ...`
- `assistant: ...`
- `system: ...`

Important rule:

- use `|` for multiline `assistant` or `system` blocks, especially for `<think>` content
- do not use `>` when newlines must be preserved

### 5. Parallel Block

```yaml
- bootstrap:
    in_parallel:
      - analyzer -> $claims:
          prompt: claims($input)
      - generator -> $answer:
          prompt: $input
```

Meaning:

- run nested steps concurrently
- wait for all outputs

### 6. For Loop

```yaml
- for $entity in $entity_nodes:
    - generator -> $end_line:
        continue:
          - user: numbered($answer)
          - assistant: |
              <think>
              Описание "{$entity.title}" заканчивается на строке "
        temperature: 0.1
        max_tokens: 10
        stop: ["\n", "\"", " "]

    - $entity.answer = slice_lines($answer, $entity.startNum, $end_line)
```

Meaning:

- iterate over collection
- execute nested steps for each item

### 7. ComfyUI Generation

```yaml
- comfyui:
    workflow: "path/to/workflow.json"
    node: "6"
    field: "text"
    value: $entity.answer
    server: "http://127.0.0.1:8188"
    timeout: 300
    export: $entity.imageUrl
```

Submits a ComfyUI workflow with injected value, polls for completion, returns image URL.

### 9. Parse Step

```yaml
- parse_claims:
    from: $claims
    export: [$entities, $axioms, $hypotheses]
```

```yaml
- parse_table:
    from: $table
    into: @root.entities
    export: $entity_nodes
```

Meaning:

- run deterministic parser, not an LLM call

Common keys:

- `from`
- `into`
- `export`

## Expressions

Supported expression kinds:

### Literal

```yaml
"text"
123
true
```

### Variable

```yaml
$answer
$entity.title
@root.answer
```

### Function Call

```yaml
claims($input)
table($answer)
numbered($answer)
concat($axioms, $hypotheses)
slice_lines($answer, $start, $end)
```

### Interpolated String

```yaml
"Verification: {$item.text}"
```

## Builtin Functions

Minimal builtin set:

- `claims(x)`
- `table(x)`
- `numbered(x)`
- `concat(a, b, ...)`
- `slice_lines(text, start, end)`
- `join(list, sep)`
- `len(x)`
- `unique(x)`

## Mode Semantics

### `prompt`

Standard LLM call. New conversation, full generation until EoT.

### `continue`

Continue an existing assistant turn. Uses `continue_assistant_turn: true`.
Runs until model emits EoT. For full-length generation in existing context.

### `probe_continue`

KV-cache optimized extraction/probing path. Injects into assistant turn
(typically inside `<think>` block), stops at `stop` tokens, reads short answer.

This is a **transport/execution primitive**, not a reasoning primitive.
It is model-family specific.

```yaml
- generator -> $result:
    mode: probe_continue
    profile: qwen_fastpath
    grammar: "[0-9]+"
    messages:
      - user: ...
      - assistant: |
          <think>
          ...injected question...
    max_tokens: 3
    temperature: 0.1
```

When `grammar` is specified, the model can ONLY generate tokens matching the GBNF rule.
This replaces `stop` tokens for format-constrained probes (numbers, booleans).

Grammar examples:
- `"[0-9]+"` — digits only (line numbers)
- `"[01]"` — single bit (true/false confirmation)
- `"(true|false)"` — boolean string

### Profiles

A `profile` declares model-specific assumptions for `probe_continue`:

| Profile | Assumptions |
|---|---|
| `qwen_fastpath` | continuation stable, think-prefix stable, stop-set tuned, output length tiny, KV cache hit near-instant, temperature 0.1 recommended, Qwen 9B best tested model for this mode |

Future profiles:

- `llama_fastpath` — if Llama supports stable think continuation
- `mistral_fastpath` — if Mistral supports stable think continuation
- `qwen_strict_probe` — stricter stop conditions, verified output format

### When to use `probe_continue`

Use when:

- answer is 1-10 tokens (line number, true/false, single word)
- context is already in KV cache (continuation of same conversation)
- model supports stable `<think>` prefix continuation
- `stop` tokens reliably terminate at answer boundary

Do not use when:

- answer requires full reasoning (use `continue` instead)
- model family does not support stable think continuation
- output format is unpredictable
- context has changed since last call (KV cache miss = no speed benefit)

## Canonical Example

```yaml
dsl: workflow/v2

let:
  input: >
    написать 4 описания внешности демонши в разных образах
    [проверить, что разные образы, разный цвет глаз,
    разный цвет волос, разные позы]

flow:
  - bootstrap:
      in_parallel:
        - analyzer -> $claims:
            prompt: claims($input)
            temperature: 0.1
            max_tokens: 2048
        - generator -> $answer:
            prompt: $input
            temperature: $settings.temperature
            max_tokens: $settings.max_tokens

  - parse_claims:
      from: $claims
      export: [$entities, $axioms, $hypotheses]

  - @root.answer = $answer

  - analyzer -> $table:
      prompt: table($answer)
      temperature: 0.1
      max_tokens: 2048

  - parse_table:
      from: $table
      into: @root.entities
      export: $entity_nodes

  - for $entity in $entity_nodes:
      - generator -> $endLineNumber:
          mode: probe_continue
          messages:
            - user: numbered($answer)
            - assistant: |
                <think>
                Разделю текст на блоки.
                Описание "{$entity.title}" начинается со строки
                под номером "{$entity.startNum}" "{$entity.firstLineText}"
                и длится до строки под номером "line number:
          stop: ["\n", "\"", " "]
          max_tokens: 10
          temperature: 0.1
      - $entity.answer = slice_lines($answer, $entity.startNum, $endLineNumber)

  - for $item in concat($axioms, $hypotheses):
      - analyzer -> $item.verdict:
          mode: probe_continue
          messages:
            - user: $answer
            - assistant: |
                <think>
                Summary table:
                {$table}

                Verification:
                (({$item.text}) == 1) ===
          stop: ["\n"]
          max_tokens: 100
          temperature: 0.1

triggers:
  check:
    - for $entity in $entity_nodes:
        - analyzer -> $entity.reaction:
            prompt: |
              Evaluate this text. Reply PASS if good, FAIL + reason if not.

              {$entity.answer}
```

## Generation Rules For Workers

When an LLM worker writes this DSL:

- output YAML only
- do not add prose around the YAML
- prefer compact steps
- use `in_parallel` for independent calls
- use `for` for repeated per-entity operations
- use `parse_*` for deterministic parsing stages
- use `|` for multiline assistant/system blocks

Avoid:

- Python code
- free-form prose comments
- implicit hidden state
- folded `>` blocks for multiline think prompts
