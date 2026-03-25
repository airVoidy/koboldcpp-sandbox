# Session Summary — 2026-03-25 (Part B: Atomic Tasks)

## What We Built
Atomic Tasks creator mode page with server-side tool execution, pipeline DSL, and reactive triggers.

## Architecture
- **Server**: `/api/atomic/run` (single tool), `/api/atomic/scope` (batch with local vars)
- **Client**: thin display layer, calls server for all tools
- **Tools**: slice, split, parse, generate, claims — all server-side
- **Scope**: batch execution, `$ref` between steps, compose export, dependency triggers

## Key Features
- **Entity system**: 4 primitives (tags, text_areas, data_areas, reactions)
- **@ref syntax**: unified `@name.field` for prompts, messages, tools
- **Pipeline DSL**: serialize steps to text, replay from scratch
- **Reactive triggers**: `on @dep1, @dep2: action` — fires when deps ready
- **Scope**: local vars, no intermediates in output, one HTTP request
- **Visible params**: all LLM call parameters shown in UI, collapsible debug
- **System messages**: dim log for tool status, separate from data cards
- **Editable messages**: pipeline = sequence of editable nodes

## Server Endpoints
- `POST /api/atomic/run` — {tool, params, workers, settings, role}
- `POST /api/atomic/scope` — {steps[], export, workers, settings}
  - steps: [{tool, params, out?, on?}]
  - export: list ["name"] or dict {"out": {"field": "$ref.field"}}
  - on: ["$dep1", "$dep2"] — wait for deps before running

## Pipeline Example (clean, no hardcode)
```
@input: написать 4 описания внешности демониц...
generate(@input) → @input_answer
generate(@claims_prompt, analyzer) → @claims_prompt_answer
scope(3x parse) → @input_constraints {entities, axioms, hypotheses}
```

## What's Next
- Global Params UI: + Table, + Text Area, + Key:Value buttons
- `@config.input` / `@config.prompt_claims` — all through config, no manual text
- Resolved preview: show @ref substitution result in entity card
- Wire client scope_begin/scope_end to server /api/atomic/scope
- table-as-query via scope
- Transposed verification

## Commits This Session
- 240dc31 Unify prompt template syntax: @ref slots
- 26697b2 Replace prompt() with showNamePopup
- 280dc0c Separate system log from tool cards
- 881008d Add explicit continue flag
- cb85608 Add slice/split tools (client prototype)
- c49ef4f Add /api/atomic/run server endpoint
- cdf4338 Wire JS tools to server API
- b45765c Move tool details to meta params
- e51b292 Migrate toolGenerate to server
- 6169e97 Prefix claims entities with source name
- 6e4624b Make message content editable
- 7c2dd85 Add parse tool (slice+split combined)
- 2846d4d Add /api/atomic/scope for batched execution
- d0d10e6 Support dict export in scope
- e2f996e Add reactive triggers
