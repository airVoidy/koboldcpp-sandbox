# Pipeline DSL Specification

## Overview
Declarative DSL for composing LLM tool pipelines. Each line is one operation. Order = execution order. All data flows through named entities (`@name`).

## Entity References

| Syntax | Meaning |
|--------|---------|
| `@name` | Entity in scope |
| `@config.name` | Global Params text area / key:value |
| `@name.field` | Entity's text_area or data_area by name |

## Operations

### 1. Bind — create entity from config or literal
```
@input = @config.input
@prompt = @config.prompt_claims
@note = "some literal text"
```
Creates entity, stores raw ref as `content`. If `@config.*`, resolved text stored as `resolved` preview.

### 2. Generate — LLM call, result assigned to new entity
```
@answer = generate(@input)
@answer = generate(@input, analyzer)
@answer = generate(@input, analyzer, no_think:false)
@claims = generate(@config.prompt_claims, analyzer, input:@config.input)
```

**Full form with assignment:**
```
@result = generate @source(slot1=@value1, no_think=false, temperature:0.2)
```

**Options (comma-separated after source):**
| Option | Default | Description |
|--------|---------|-------------|
| `analyzer`/`generator`/`verifier` | generator | Worker role |
| `no_think:false` | true for prompt mode | Allow think block |
| `temperature:0.6` | from $params | Override temperature |
| `max_tokens:2048` | from $params | Override max tokens |
| `mode:prompt` | prompt | prompt / continue / probe_continue |
| `grammar:$grammar.name` | none | GBNF grammar constraint |
| `stop:"\\n"` | none | Stop sequences |
| `input:@ref` | none | Slot mapping: @input in template → @ref |

**Result:** Creates `@source_answer` entity (or `@result` if assigned).

### 3. Parse Sections — extract structured data from delimited text
```
parse_sections(@source, DELIM1:, DELIM2:, DELIM3:)
```

**Declarative form:**
```
parse @output.(field1, field2, field3) from @source(DELIM1..DELIM2, DELIM2..DELIM3, DELIM3..)
```

Calls server `/api/atomic/scope` with slice+split between consecutive delimiters. Result: entity `@output` with data_areas per field.

**Delimiter ranges:**
- `DELIM1..DELIM2` — text between DELIM1 and DELIM2
- `DELIM3..` — text from DELIM3 to end

### 4. Tag — annotate entity with key:value metadata
```
tag(@entity, key, value)
```

### 5. Scope — client-side entity scope management
```
scope_begin()
scope_end(@keep1, @keep2)
drop(@entity)
```

### 6. Structural — create entities and tables
```
add_entity(@name)
add_text(@entity, area_name, text content)
add_table(@entity, table_name, Col1, Col2, Col3)
rename(@entity, new_name)
```

### 7. Macros — save and replay command sequences
```
save_macro(name)
run_macro(name)
list_macros()
delete_macro(name)
```

### 8. Export
```
export_dsl(pipeline_name)
```

## Full Pipeline Example

### Setup (Global Params)
- `@config.input` — task text: "написать 4 описания внешности демониц..."
- `@config.prompt_claims` — claims extraction prompt template with `@input` slot

### Pipeline
```
# Pipeline: demoness_analysis

# 1. Bind input from config
@input = @config.input

# 2. Generate descriptions
generate(@input)

# 3. Extract claims using analyzer with prompt template
generate(@config.prompt_claims, analyzer)

# 4. Parse claims into structured sections
parse_sections(@prompt_claims_answer, ENTITIES:, AXIOMS:, HYPOTHESES:)
```

### Declarative form (equivalent)
```
@input = @config.input
@input_answer = generate(@input)
@claims = generate(@config.prompt_claims, analyzer)
parse @claims_constraints.(entities, axioms, hypotheses) from @claims(ENTITIES:..AXIOMS:, AXIOMS:..HYPOTHESES:, HYPOTHESES:..)
```

## Available Workers
| Role | Purpose | Typical use |
|------|---------|-------------|
| generator | Creative text generation | generate(@input) |
| analyzer | Structured extraction, logic | claims, parse prompts |
| verifier | Fact-checking, validation | verify(@table, @axioms) |

## Server Endpoints
- `POST /api/atomic/run` — single tool: `{tool, params, workers, settings, role}`
- `POST /api/atomic/scope` — batch: `{steps[], export, workers, settings}`

## Notes for LLM Pipeline Generation
- Every `generate()` creates `@source_answer` entity automatically
- `@config.*` refs are resolved at call time (multi-pass, up to 5 levels)
- Slot mappings in generate: `input:@config.input` replaces `@input` in template
- `parse_sections` uses server scope — one HTTP call for all sections
- Pipeline steps are recorded and can be exported/saved as macros
