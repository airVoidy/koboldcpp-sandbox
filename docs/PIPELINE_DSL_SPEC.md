# Atomic DSL Spec

## Goal
Compact DSL for Atomic Tasks pipelines. One line is one statement. The language has two layers:

- Runtime DSL: entities, tool calls, reactive triggers
- Editor commands: macros, export, rename, drop

Editor commands are prefixed with `/` and are not part of exported pipelines.

## Names

| Syntax | Meaning |
|---|---|
| `@name` | Local entity |
| `@name.field` | Entity field |
| `$config.name` | Global param |

## Runtime Statements

### Value Assignment
```pipeline
@input = $config.input
@note = "short text"
@prompt = """multi
line
text"""
```

### Tool Assignment
```pipeline
@answer = generate(@input)
@claims = generate($config.prompt_claims, worker:analyzer, input:@input, think:true)
@sections = parse_sections(@claims, entities:"ENTITIES:", axioms:"AXIOMS:", hypotheses:"HYPOTHESES:")
@list = split(@answer)
@slice = slice(@answer, "FROM:", "TO:")
@cols = concat(@sections.entities, @sections.axioms)
@header = join(@cols, sep:" | ", prefix:"| ", suffix:" |")
```

### In-Place Calls
```pipeline
tag(@sections, kind:"constraints")
untag(@sections, kind)
set_text(@chat, assistant, "<think>\n\n</think>\n\n")
append_text(@chat, assistant, @draft.answer)
verify(@table_a, @table_b)
```

### Reactive Triggers
```pipeline
on @input -> @answer = generate(@input)
on @answer -> @sections = parse_sections(@answer, entities:"ENTITIES:", axioms:"AXIOMS:")
```

### Loop Block
```pipeline
loop(while:@need_more, max_iters:4) {
  @parsed = parse_table(@table)
  @rows = row_count(@parsed)
  @need_more = lt(@rows, $config.target_rows)
}
```

Rules:
- `while:@cond` is required
- `max_iters` is optional, default `8`
- loop body runs with normal DSL semantics
- body steps are not re-recorded as top-level pipeline steps on each iteration

## Tool Calls

### `generate`
```pipeline
@out = generate(@source, worker:analyzer, input:@input, think:true)
```

Supported options:
- `worker:generator|analyzer|verifier`
- `think:true|false`
- `temperature:0.2`
- `max_tokens:2048`
- `mode:prompt|continue|probe_continue`
- `continue:true|false`
- `input:@ref`
- `grammar:$grammar.name`
- `stop:"\n"`
- `capture:"regex"`
- `coerce:"type"`

Backward-compatible legacy forms still parse:
```pipeline
generate(@source, analyzer)
generate(@source, analyzer, no_think:false)
```

### `parse_sections`
```pipeline
@sections = parse_sections(
  @claims,
  entities:"ENTITIES:",
  axioms:"AXIOMS:",
  hypotheses:"HYPOTHESES:"
)
```

Rules:
- Named sections are preferred
- Positional delimiters still work
- Result is one entity with fields per section
- Without explicit assignment, default output is `@source_constraints`

### Local Pure Transforms
These run locally and do not call an LLM:

```pipeline
@cols = concat(@a, @b)
@md_head = table_header(@entities, @axioms)
@cols1 = prepend(@cols, "#")
@header = join(@cols1, sep:" | ", prefix:"| ", suffix:" |")
@hyp_line = join_list(@hypotheses, sep:" | ")
@count = len(@cols1)
@sep_cells = repeat("---", count:@count)
@grid = chunk(@items, size:2)
@grid2 = reshape_grid(@answer, cols:2)
@body = lines(@header, @sep)
@parsed = parse_table(@table)
@rows = row_count(@parsed)
@labels = get_column(@parsed, "prompt")
@row_items = split_rows(@parsed, "prompt")
@need_more = lt(@rows, @target_rows)
@continue_token = guard(@need_more, "continue")
@accepted = accepted_list(@table, checks:@axioms)
@rejected = reject_reasons(@table, checks:@axioms)
@accepted_rows = filter_rows(@table, where:all_yes, checks:@axioms)
```

Supported transforms:
- `concat(@a, @b, ...)`
- `table_header(@entities, @axioms, ...)`
- `prepend(@list, value1, ...)`
- `join(@list, sep:"...", prefix:"...", suffix:"...")`
- `join_list(@list, sep:"...")`
- `len(@value)`
- `repeat(value, count:@n)`
- `chunk(@list, size:2)`
- `reshape_grid(@value, cols:2)`
- `lines(@a, @b, ...)`
- `parse_table(@entity_or_text)`
- `row_count(@table)`
- `get_column(@table, "column")`
- `split_rows(@table, "label_column")`
- `add(@a, @b)`
- `sub(@a, @b)`
- `eq(@a, @b)`
- `lt(@a, @b)`
- `lte(@a, @b)`
- `gt(@a, @b)`
- `gte(@a, @b)`
- `not(@cond)`
- `guard(@cond, @value)`
- `filter_rows(@table, where:all_yes, checks:@axioms)`
- `reject_reasons(@table, checks:@axioms)`
- `accepted_list(@table, checks:@axioms)`

Rules:
- flat `data_area`s like `['#', 'Value']` resolve as plain lists
- markdown tables in text areas are parsed as tables for row filters
- nested transform results are stored back as grid-like `data_area`s
- `guard` is the minimal control primitive: it emits nothing when the condition is false
- `table_header`, `reshape_grid`, `join_list`, `filter_rows`, `reject_reasons`, and `accepted_list` are convenience sugar over the same local transform layer
- `parse_table`, `row_count`, `get_column`, and `split_rows` are the lower-level table wrappers to compose larger verdict flows

### Other Output-Producing Tools
These also support explicit assignment:
```pipeline
@n = numbered(@text)
@slice = slice(@text, "FROM:", "TO:")
@items = split(@text)
@table = table_as_query(@text, col1, col2)
@probe = probe_continue(@text, mode:probe_continue)
@t = transpose(@table)
```

### Message Mutation
Use these for staged assistant continuation flows:
```pipeline
set_text(@chat, user, $config.prompt)
set_text(@chat, assistant, "<think>\n\n</think>\n\n")
append_text(@chat, assistant, @draft.answer)
append_text(@chat, assistant, @table_head)
```

Rules:
- `set_text` replaces or creates one named text area
- `append_text` appends to an existing text area
- values can be literals, `$config.*`, `@entity`, or `@entity.field`
- when the last message is an `assistant` field, `generate(..., mode:continue)` continues that assistant turn

## Editor Commands

```text
/save_macro(name)
/run_macro(name)
/export_dsl(name)
/rename(@old, new_name)
/drop(@entity)
/list_macros()
/delete_macro(name)
```

## Export Rules

- Exported pipelines contain runtime statements only
- `$config.*` is preferred over `@config.*` in exported text
- Explicit assignment is preferred over implicit `@source_answer`
- `untag` is preferred over `remove_tag`

## Example

```pipeline
@input = $config.input

@draft = generate(@input)

@claims = generate(
  $config.prompt_claims,
  worker:analyzer,
  input:@input,
  think:true
)

@sections = parse_sections(
  @claims,
  entities:"ENTITIES:",
  axioms:"AXIOMS:",
  hypotheses:"HYPOTHESES:"
)

tag(@sections, kind:"logic_constraints")
```

## Staged Example

```pipeline
@chat = "session"
set_text(@chat, user, $config.prompt)
set_text(@chat, assistant, "<think>\n\n</think>\n\n")

@draft = generate(
  @chat,
  mode:continue,
  continue:true,
  temperature:0.6,
  max_tokens:2048
)

@claims = generate(
  $config.prompt_claims,
  worker:analyzer,
  input:$config.prompt,
  think:true
)

@constraints = parse_sections(
  @claims,
  entities:"ENTITIES:",
  axioms:"AXIOMS:",
  hypotheses:"HYPOTHESES:"
)

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

@table = generate(
  @chat,
  mode:continue,
  continue:false,
  temperature:0.1,
  max_tokens:1024,
  stop:"\n\n\n"
)
```

## Notes

- Triple-quoted assignment is supported in pipeline execution
- Multi-line fenced code blocks using ```pipeline are supported
- Triggers are exported as declarative `on ... -> ...` statements
- `loop(...) { ... }` is a client-side DSL wrapper for repeated execution
- Server scope remains an implementation detail behind `parse_sections`
- Server-side loop is available as a lower-level runtime primitive via `/api/atomic/loop`
- See `ATOMIC_DSL_RECIPES.md` for staged continuation and transform patterns
