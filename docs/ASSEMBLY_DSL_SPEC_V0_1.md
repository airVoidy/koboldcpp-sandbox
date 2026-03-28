# Assembly DSL Spec v0.2

## Purpose

Assembly DSL is the low-level layer of Atomic DSL.

It provides a minimal, flat instruction set for small chains (3-8 ops) that can be wrapped into higher-level semantic functions.

## Design Principles

1. Fixed small instruction set (10 opcodes)
2. Flat execution — no nesting, no blocks (EACH body is specified by +N count)
3. Positional + flag syntax: `OPCODE dst, src, flag:val`
4. One line = one instruction
5. Chains are short, wrapped by `fn` declarations
6. DSL-level function library: prompt templates and compositions stored as wiki pages

## Relation to Multi-Layer Model

From `ATOMIC_MULTI_LAYER_DSL_MODEL.md`:

- **Semantic layer** — compact named functions (`staged_answer`, `verify_uniqueness`)
- **Assembly layer** — this spec: MOV/GEN/PUT/PARSE/CALL/CMP/JIF/LOOP/EACH/NOP
- **Runtime layer** — worker call construction, endpoint requests, checkpoint hooks

Assembly is the middle layer. It is explicit enough to inspect but compact enough to compose.

## Namespaces

Same as Pipeline DSL:

| Syntax | Meaning |
|---|---|
| `@name` | Local entity (register) |
| `@name.field` | Entity field access |
| `$config.name` | Global parameter (constant) |

## Comments

```asm
; this is a comment
MOV @x, 42  ; inline comment
```

## Instruction Set

### MOV — copy/assign

```asm
MOV  dst, src
```

Examples:
```asm
MOV  @input, $config.input
MOV  @note, "literal text"
MOV  @x, @y.field
MOV  @count, 0
```

### GEN — LLM generate

```asm
GEN  dst, src [, flags...]
```

The expensive syscall. All generate modes unified under one opcode.

Flags:
- `mode:prompt|continue|probe` — generation mode (default: `prompt`)
- `worker:generator|analyzer|verifier` — worker type (default: `generator`)
- `temp:0.6` — temperature
- `max:2048` — max tokens
- `think:true|false` — enable think block
- `stop:"\n"` — stop sequence
- `cap:"regex"` or `capture:"regex"` — capture regex for probe results
- `coerce:int|float` — type coercion for probe results (use with capture)
- `grammar:$ref` — GBNF grammar ref
- `input:@ref` — additional input binding

When `mode:probe` and `capture`/`coerce` are set, the raw LLM output is post-processed:
1. Cleaned (strip whitespace, collapse to first line)
2. Capture regex applied → extract match
3. Coerce type applied → int or float

Examples:
```asm
GEN  @draft, @chat
GEN  @draft, @chat, mode:continue, temp:0.6, max:2048
GEN  @claims, @input, worker:analyzer, think:true
GEN  @probe, @chat, mode:probe, stop:"\n", cap:"yes|no"
GEN  @line_num, @chat, mode:probe, grammar:$digit_grammar, capture:"[0-9]+", coerce:int, temp:0, max:4
```

### PUT / PUT+ — message mutation

```asm
PUT   target, role, value     ; set (replace)
PUT+  target, role, value     ; append
```

Examples:
```asm
PUT   @chat, user, $config.prompt
PUT   @chat, assistant, "<think>\n\n</think>\n\n"
PUT+  @chat, assistant, @draft.answer
PUT+  @chat, assistant, "\n\n"
```

### PARSE — extract structured data

```asm
PARSE  dst, src, pattern_flag
```

Pattern flags:
- `sections:"LABEL1:|LABEL2:|LABEL3:"` — parse labeled sections
- `split:"delimiter"` — split text into list
- `from:"START:", to:"END:"` — slice between markers
- `table:true` — parse markdown table
- `regex:"pattern"` — extract via regex
- `coerce:int|float|bool` — type coercion (combine with regex)

Examples:
```asm
PARSE  @sections, @claims, sections:"ENTITIES:|AXIOMS:|HYPOTHESES:"
PARSE  @items, @text, split:"\n"
PARSE  @slice, @text, from:"## Answer", to:"## End"
PARSE  @table, @text, table:true
PARSE  @val, @text, regex:"\\d+", coerce:int
```

### CALL — invoke pure transform or function

```asm
CALL  dst, fn_name, args... [, flags...]
```

All 26+ Pipeline DSL transforms are available as CALL targets. User-defined and Python-defined functions are also callable.

Examples:
```asm
CALL  @cols, concat, @a, @b
CALL  @header, join, @cols, sep:" | ", prefix:"| ", suffix:" |"
CALL  @n, len, @cols
CALL  @top3, take, @items, count:3
CALL  @sorted, sort, @items, mode:text
CALL  @filtered, filter_rows, @table, where:all_yes, checks:@axioms
CALL  @result, staged_answer, @chat, $config.prompt
```

### CMP — compare

```asm
CMP  dst, op, a, b
```

Operators: `eq`, `ne`, `lt`, `lte`, `gt`, `gte`

Result is boolean, stored in dst.

Examples:
```asm
CMP  @need_more, lt, @rows, $config.target_rows
CMP  @ok, eq, @probe.answer, "yes"
CMP  @done, gte, @count, 10
CMP  @diff, ne, @a, @b
```

### JIF — conditional skip

```asm
JIF  cond, +N
```

If `cond` is truthy, skip the next N instructions.

Use for "if done, skip the repair block" patterns:

```asm
CMP  @ok, eq, @status, "done"
JIF  @ok, +2
PUT+ @chat, assistant, @more
GEN  @more, @chat, mode:continue
; execution continues here after skip or after GEN
```

### LOOP — bounded repeat

```asm
LOOP  cond, max_iters, +N
```

Repeat the next N instructions while `cond` is truthy, up to `max_iters` times.

The condition is re-evaluated after each iteration (the body must update it).

```asm
LOOP @need_more, 4, +5
PUT+ @chat, assistant, @table.answer
GEN  @table, @chat, mode:continue, temp:0.1, stop:"\n\n\n"
PARSE @parsed, @table, table:true
CALL @rows, row_count, @parsed
CMP  @need_more, lt, @rows, $config.target_rows
```

### EACH — iterate collection

```asm
EACH  @item, @collection, +N
```

Iterate over each element in `@collection`, binding it to `@item`, and execute the next N instructions as the loop body.

For dict items: `@item._index` is set to the 0-based iteration index. Fields modified on `@item` (e.g., `@item.status`) are written back to the collection.

```asm
EACH @entity, @entity_nodes, +3
  CALL @entity.answer, slice_lines, @answer, @entity._startNum, @entity._endNum
  CALL @entity.status, check_status, @entity.reaction
  MOV  @entity.processed, true
```

Nested EACH is supported:
```asm
EACH @entity, @entities, +2
  EACH @constraint, @constraints, +1
    CALL @ann, create_span_annotation, @entity, @constraint, @start, @end
```

### NOP — no operation

```asm
NOP
```

Does nothing. Useful as padding or placeholder.

## Function Declarations

### DSL-defined functions

```asm
fn name(params...) -> outputs...:
  OPCODE ...
  OPCODE ...
```

Parameters use `@` or `$` prefixes. Outputs are listed after `->`.

Example:
```asm
fn staged_answer(@chat, $prompt, $claims_prompt) -> @draft, @constraints:
  MOV   @chat, "session"
  PUT   @chat, user, $prompt
  PUT   @chat, assistant, "<think>\n\n</think>\n\n"
  GEN   @draft, @chat, mode:continue, temp:0.6
  GEN   @claims, $claims_prompt, worker:analyzer, think:true
  PARSE @constraints, @claims, sections:"ENTITIES:|AXIOMS:|HYPOTHESES:"
```

### Python-defined functions

```python
from kobold_sandbox.assembly_functions import asm_function

@asm_function("staged_answer", params=["@chat", "$prompt", "$claims_prompt"], outputs=["@draft", "@constraints"])
def staged_answer(ctx):
    ctx.mov("@chat", "session")
    ctx.put("@chat", "user", ctx.resolve("$prompt"))
    ctx.put("@chat", "assistant", "<think>\n\n</think>\n\n")
    ctx.gen("@draft", "@chat", mode="continue", temp=0.6)
    ctx.gen("@claims", ctx.resolve("$claims_prompt"), worker="analyzer", think=True)
    ctx.parse("@constraints", "@claims", sections="ENTITIES:|AXIOMS:|HYPOTHESES:")
```

Both are invoked the same way:
```asm
CALL @result, staged_answer, @chat, $config.prompt, $config.claims_prompt
```

## Comparison with Pipeline DSL

| Pipeline DSL | Assembly DSL | Notes |
|---|---|---|
| `@x = generate(...)` | `GEN @x, ...` | Unified opcode |
| `@x = concat(@a, @b)` | `CALL @x, concat, @a, @b` | All transforms via CALL |
| `set_text(@chat, user, ...)` | `PUT @chat, user, ...` | Shorter |
| `append_text(@chat, ...)` | `PUT+ @chat, ...` | PUT+ for append |
| `@x = parse_sections(...)` | `PARSE @x, ...` | Unified parsing |
| `@x = $config.input` | `MOV @x, $config.input` | Explicit opcode |
| `loop(while:@c, max:4) { }` | `LOOP @c, 4, +N` | Flat, no braces |
| `on @x -> ...` | *(semantic layer)* | Not in assembly |
| `tag/untag` | *(semantic layer)* | Not in assembly |

## Full Recipe: Staged Continue + Table

Pipeline DSL version (from ATOMIC_DSL_RECIPES.md):
```pipeline
@chat = "session"
set_text(@chat, user, $config.prompt)
set_text(@chat, assistant, "<think>\n\n</think>\n\n")
@draft = generate(@chat, mode:continue, continue:true, temperature:0.6, max_tokens:2048)
@claims = generate($config.prompt_claims, worker:analyzer, input:$config.prompt, think:true)
@constraints = parse_sections(@claims, entities:"ENTITIES:", axioms:"AXIOMS:", hypotheses:"HYPOTHESES:")
@cols = concat(@constraints.entities, @constraints.axioms)
@cols1 = prepend(@cols, "#")
@header = join(@cols1, sep:" | ", prefix:"| ", suffix:" |")
@n = len(@cols1)
@sep_cells = repeat("---", count:@n)
@sep = join(@sep_cells, sep:"|", prefix:"|", suffix:"|")
@table_head = lines(@header, @sep)
append_text(@chat, assistant, @draft.answer)
append_text(@chat, assistant, "\n\n")
append_text(@chat, assistant, @table_head)
append_text(@chat, assistant, "\n| 1 |")
@table = generate(@chat, mode:continue, continue:false, temperature:0.1, max_tokens:1024, stop:"\n\n\n")
```

Assembly DSL version:
```asm
; --- init chat ---
MOV   @chat, "session"
PUT   @chat, user, $config.prompt
PUT   @chat, assistant, "<think>\n\n</think>\n\n"

; --- generate draft + constraints ---
GEN   @draft, @chat, mode:continue, temp:0.6, max:2048
GEN   @claims, $config.prompt_claims, worker:analyzer, input:$config.prompt, think:true
PARSE @constraints, @claims, sections:"ENTITIES:|AXIOMS:|HYPOTHESES:"

; --- build table header ---
CALL  @cols, concat, @constraints.entities, @constraints.axioms
CALL  @cols, prepend, @cols, "#"
CALL  @header, join, @cols, sep:" | ", prefix:"| ", suffix:" |"
CALL  @n, len, @cols
CALL  @sep_cells, repeat, "---", count:@n
CALL  @sep, join, @sep_cells, sep:"|", prefix:"|", suffix:"|"
CALL  @table_head, lines, @header, @sep

; --- append and continue ---
PUT+  @chat, assistant, @draft.answer
PUT+  @chat, assistant, "\n\n"
PUT+  @chat, assistant, @table_head
PUT+  @chat, assistant, "\n| 1 |"
GEN   @table, @chat, mode:continue, temp:0.1, max:1024, stop:"\n\n\n"
```

Or using semantic functions:
```asm
CALL  @draft, @constraints, staged_answer, @chat, $config.prompt, $config.prompt_claims
CALL  @table_head, build_table_header, @constraints
CALL  @table, @parsed, continue_to_target, @chat, @table_head, $config.target_rows
```

## Execution Model

1. Instructions execute sequentially by instruction pointer (IP)
2. JIF advances IP by +N+1 when condition is true
3. LOOP saves IP, executes body, re-checks condition, jumps back or advances
4. GEN is blocking (waits for LLM response)
5. CALL to a function creates a child scope, executes, returns outputs
6. All state is in the entity map (`@` refs) and config (`$` refs)

## Function Library

DSL-level functions can be stored as wiki pages with `page_kind: "function_page"` and loaded at runtime.

### Saving a function

```
POST /api/dsl/fn/save
{
  "slug": "fn-claims",
  "title": "claims",
  "source": "fn claims(@text) -> @prompt:\n  MOV @prefix, \"Analyze: \"\n  CALL @prompt, concat, @prefix, @text",
  "tags": ["prompt-template"]
}
```

Or directly via wiki CRUD:
```
PUT /api/atomic-wiki/pages/fn-claims
{
  "title": "claims",
  "page_kind": "function_page",
  "blocks": [{"kind": "text", "label": "source", "text": "fn claims(@text) -> @prompt:\n  ..."}],
  "tags": ["function", "prompt-template"]
}
```

### Loading at execution time

The `/api/dsl/asm` endpoint can load library functions from wiki `function_page` entries. These are passed as `extra_functions` to the interpreter, making them available via `CALL`.

### Two levels of functions

1. **DSL fn** — prompt templates, compositions. Stored in wiki, defined in Assembly syntax.
2. **Python `@asm_function`** — low-level utilities (string ops, parsing). Registered via `dsl_builtins.py`:
   - `slice_lines(text, start, end)`, `numbered(text)`, `char_indexed(text)`
   - `check_status(text)`, `concat(*args)`, `parse_sections(text)`
   - `enrich_entities(entities, answer)`, `create_span_annotation(entity, constraint, start, end)`

## Probe-Based Annotation

`POST /api/dsl/annotations/probe` finds char spans for constraints in message text.

Input: message with text containers + constraint list + optional workers.

Two modes:
1. **With workers** — think-injection probes via Assembly GEN (two passes: start, end)
2. **Without workers** — regex fallback (substring search)

Output: message with annotations added (char_start/char_end/char_len).

## API Endpoint

```
POST /api/atomic/asm
{
  "code": "MOV @x, 42\nCALL @y, len, @x",
  "config": {"input": "hello world"},
  "state": {}
}

Response:
{
  "state": {"x": 42, "y": 11},
  "log": [
    {"ip": 0, "op": "MOV", "status": "done"},
    {"ip": 1, "op": "CALL", "status": "done"}
  ],
  "error": null
}
```
