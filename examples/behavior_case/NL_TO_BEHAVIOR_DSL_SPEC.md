# Natural Language To Behavior DSL Spec

## Goal

This spec is the **full context** for an LLM worker that converts a natural-language task into a fully serialized `BehaviorTree` JSON.

The worker should not write Python code.
It should produce a complete JSON tree with:

- `BehaviorTree` (top-level structure)
- `BehaviorNode` (each work unit)
- `BehaviorElement` (each step within a node, using `__dsl__` handler)
- `BehaviorClaim` (validation rules, preferably DSL-based)
- prompt templates and routing — all in JSON

The runtime executes generic DSL commands and builtin functions only.

## Output Contract

Return one JSON object only:

```json
{
  "format_version": "behavior-tree/v1",
  "tree_id": "string",
  "root_node_id": "root",
  "global_meta": {},
  "global_claims": [],
  "bindings": {
    "profiles": {},
    "rules": []
  },
  "nodes": {}
}
```

No prose before or after JSON.

---

## Namespace Convention

### References

| Prefix | Meaning | Persistent? | Example |
|--------|---------|-------------|---------|
| `$x` | element-local runtime variable | No (dies after element) | `$prompt`, `$failures` |
| `@x` | `node.data.x` | Yes (per node) | `@draft_text`, `@style` |
| `@@x` | `tree.global_meta.x` | Yes (shared across all nodes) | `@@language`, `@@sentence_range` |
| `#x` | reserved runtime/service value | — | `#node_id`, `#tree_id` |

### Template strings

Use `{$...}` for substitution inside template strings:

```
"Style: {$@style}. Hair: {$@hair_color}."        ← node data
"Reply in {$@@language}."                         ← global meta
"Failures: {$$failures}."                          ← local variable
```

---

## Core Model

### BehaviorTree

- `format_version`: `"behavior-tree/v1"`
- `tree_id`: unique string
- `root_node_id`: usually `"root"`
- `global_meta`: shared settings (`language`, `sentence_range`, `temperature`, `creative_agent`, etc.)
- `global_claims`: tree-wide validation rules
- `bindings`: agent profiles and rules
- `nodes`: dict of `node_id` → `BehaviorNode`

### BehaviorNode

- `node_id`: unique within tree
- `kind`: category string (e.g. `"generated_item"`, `"auto_root"`)
- `entry_element`: which element to start execution at
- `elements`: ordered list of `BehaviorElement`
- `data`: persistent key-value storage (accessible as `@field`)
- `meta`: metadata (instruction bundles, etc.)
- `return_key`: which `@field` to return when node completes
- `claims`: list of `BehaviorClaim`

### BehaviorElement

```json
{
  "element_id": "local_check",
  "handler": "__dsl__",
  "transitions": {"fail": "repair", "pass": "compress"},
  "meta": {
    "do": [...]
  }
}
```

- `element_id`: unique within node
- `handler`: always `"__dsl__"` for DSL elements
- `transitions`: outcome → next element_id mapping
- `meta.do`: list of DSL commands to execute

### BehaviorClaim

```json
{
  "claim_id": "item-01-hair-color",
  "owner_node_id": "item-01",
  "scope": "node",
  "evaluator": "__dsl__",
  "meta": {
    "dsl": {
      "pending_if": {"empty": {"coalesce": ["@final_text", "@draft_text"]}},
      "test": {"contains": [{"coalesce": ["@final_text", "@draft_text"]}, "@hair_color"]},
      "pass": "hair color present",
      "fail": "hair color missing"
    }
  }
}
```

---

## DSL Commands

All commands go inside `meta.do` as a list of objects.

### `set` — assign values

```json
{"set": {"$x": 1, "@status": "pending", "@@mode": "strict"}}
```

Supports `{"inc": "@field"}` for increment:
```json
{"set": {"@repair_count": {"inc": "@repair_count"}}}
```

### `save` — copy local variable to persistent storage

```json
{"save": {"@local_failures": "$failures", "@final_text": "$result"}}
```

### `copy` — copy one field to another

```json
{"copy": {"from": "@draft_text", "to": "@final_text"}}
```

### `render` — expand template string

```json
{"render": {"to": "$prompt", "template": "Style: {$@style}. Hair: {$@hair_color}. Reply in {$@@language}."}}
```

### `call` — invoke a builtin function

```json
{"call": {"fn": "truncate_sentences", "args": {"text": "@draft_text", "range": "@sentence_range"}, "to": "$final"}}
```

```json
{"call": {"fn": "call_agent", "args": {"agent": "@@creative_agent", "prompt": "$prompt", "system": "$system"}, "to": "$text"}}
```

### `claims` — evaluate claims, get failures

```json
{"claims": "$local_failures"}
```

```json
{"claims": {"scope": "tree", "to": "$global_failures"}}
```

### `if` — conditional branching

```json
{
  "if": {
    "test": {"empty": "$local_failures"},
    "then": [{"outcome": "pass"}],
    "else": [{"outcome": "fail"}]
  }
}
```

### `for_each` — loop over list

```json
{
  "for_each": {
    "in": "@child_ids",
    "as": "$child_id",
    "do": [
      {"run_node": {"node_id": "$child_id", "to": "$record"}},
      {"append": {"to": "$outputs", "value": "$record"}}
    ]
  }
}
```

### `append` — add to list

```json
{"append": {"to": "$outputs", "value": "$text"}}
```

### `run_node` — execute another node

```json
{"run_node": {"node_id": "$child_id", "to": "$record"}}
```

### `collect` — gather field from multiple nodes

```json
{"collect": {"from_nodes": "@child_ids", "field": "final_text", "to": "$outputs"}}
```

### `outcome` — set element outcome (controls transitions)

```json
{"outcome": "pass"}
```

### `return` — set node return value

```json
{"return": "@final_text"}
```

### `halt` — stop execution

```json
{"halt": true}
```

### `log` — diagnostic message

```json
{"log": "Processing node {$#node_id}, style: {$@style}"}
```

---

## Predicates

Used inside `if.test`. Each predicate takes refs as arguments.

| Predicate | Args | Example |
|-----------|------|---------|
| `empty` | value | `{"empty": "$failures"}` |
| `not_empty` | value | `{"not_empty": "@draft_text"}` |
| `eq` | [a, b] | `{"eq": ["@status", "pass"]}` |
| `ne` | [a, b] | `{"ne": ["@status", "fail"]}` |
| `gt` | [a, b] | `{"gt": ["$count", 5]}` |
| `gte` | [a, b] | `{"gte": ["$score", 7]}` |
| `lt` | [a, b] | `{"lt": ["$count", 3]}` |
| `lte` | [a, b] | `{"lte": ["$count", 10]}` |
| `contains` | [haystack, needle] | `{"contains": ["@draft_text", "@hair_color"]}` |
| `in` | [value, list] | `{"in": ["$color", "@allowed_colors"]}` |
| `in_range` | [value, [min, max]] | `{"in_range": ["$count", [5, 10]]}` |
| `all` | [pred, pred, ...] | `{"all": [{"not_empty": "@text"}, {"contains": ["@text", "@color"]}]}` |
| `any` | [pred, pred, ...] | `{"any": [{"eq": ["@status", "pass"]}, {"eq": ["@status", "skip"]}]}` |
| `not` | pred | `{"not": {"empty": "@text"}}` |

### Special values

- `{"coalesce": ["@final_text", "@draft_text"]}` — returns first non-empty value
- `{"inc": "@counter"}` — returns value + 1

---

## Builtin Functions

Use with `{"call": {"fn": "name", "args": {...}, "to": "$result"}}`.

| Function | Args | Returns | Description |
|----------|------|---------|-------------|
| `len` | `{"value": ref}` | int | Length of list/string |
| `inc` | `{"value": ref}` | int | Value + 1 |
| `split_sentences` | `{"text": ref}` | list | Split text into sentences |
| `truncate_sentences` | `{"text": ref, "range": ref}` | string | Truncate to max sentences |
| `unique` | `{"value": ref}` | list | Remove duplicates |
| `count` | `{"value": ref}` | int | Same as len |
| `node_field` | `{"node_id": ref, "field": "name"}` | any | Read field from another node |
| `call_agent` | `{"agent": ref, "prompt": ref, "system": ref, "temperature": float, "max_tokens": int, "no_think": bool}` | string | Call LLM agent |
| `render_template` | `{"template": ref}` | string | Render template with current context |
| `eval_claims` | `{"scope": "node"\|"tree"}` | list | Evaluate claims, return failed ids |

### `call_agent` details

```json
{
  "call": {
    "fn": "call_agent",
    "args": {
      "agent": "@@creative_agent",
      "prompt": "$prompt",
      "system": "$system",
      "temperature": 0.7,
      "max_tokens": 1024,
      "no_think": true
    },
    "to": "$response"
  }
}
```

- `agent`: defaults to `@@creative_agent` or `"small_context_worker"`
- `no_think`: if `true`, adds prefill to skip thinking (faster, for short answers)
- For short factual checks: use `"max_tokens": 30, "no_think": true`

---

## Claim DSL

Claims should be declarative DSL expressions, not Python evaluators.

```json
{
  "claim_id": "item-01-sentence-range",
  "owner_node_id": "item-01",
  "scope": "node",
  "evaluator": "__dsl__",
  "meta": {
    "dsl": {
      "pending_if": {"empty": {"coalesce": ["@final_text", "@draft_text"]}},
      "test": {"in_range": [
        {"call": "len", "of": {"call": "split_sentences", "of": {"coalesce": ["@final_text", "@draft_text"]}}},
        "@sentence_range"
      ]},
      "pass": "sentence count in range",
      "fail": "sentence count out of range"
    }
  }
}
```

Simple form:
```json
{
  "claim_id": "item-01-hair-color",
  "owner_node_id": "item-01",
  "scope": "node",
  "evaluator": "__dsl__",
  "meta": {
    "dsl": {
      "test": {"contains": [{"coalesce": ["@final_text", "@draft_text"]}, "@hair_color"]},
      "pass": "hair color present",
      "fail": "hair color missing"
    }
  }
}
```

---

## Complete Element Patterns

### Draft (generate text via LLM)

```json
{
  "element_id": "draft",
  "handler": "__dsl__",
  "meta": {
    "do": [
      {"render": {"to": "$system", "template": "Write text as instructed. Content only, no headers or preambles."}},
      {"render": {"to": "$prompt", "template": "{$@prompt}\nStyle: {$@style}.\nRequired detail: {$@key_detail}.\nSentence range: {$@@sentence_range}.\nReply in {$@@language}. Start directly with content."}},
      {"call": {"fn": "call_agent", "args": {"prompt": "$prompt", "system": "$system"}, "to": "$text"}},
      {"save": {"@draft_text": "$text"}},
      {"set": {"@llm_generated": true}},
      {"outcome": "pass"}
    ]
  }
}
```

### Local Check

```json
{
  "element_id": "local_check",
  "handler": "__dsl__",
  "transitions": {"fail": "repair", "pass": "compress"},
  "meta": {
    "do": [
      {"claims": "$local_failures"},
      {"save": {"@local_failures": "$local_failures"}},
      {"if": {
        "test": {"empty": "$local_failures"},
        "then": [{"outcome": "pass"}],
        "else": [{"outcome": "fail"}]
      }}
    ]
  }
}
```

### Repair

```json
{
  "element_id": "repair",
  "handler": "__dsl__",
  "meta": {
    "do": [
      {"set": {"@repair_count": {"inc": "@repair_count"}}},
      {"render": {"to": "$prompt", "template": "Previous text failed.\nFailures: {$@local_failures}.\nTask: {$@prompt}\nRequired detail: {$@key_detail}.\nRewrite and fix. Reply in {$@@language}.\n\nOld text:\n{$@draft_text}"}},
      {"call": {"fn": "call_agent", "args": {"prompt": "$prompt"}, "to": "$repaired"}},
      {"save": {"@draft_text": "$repaired"}},
      {"outcome": "pass"}
    ]
  }
}
```

### Compress

```json
{
  "element_id": "compress",
  "handler": "__dsl__",
  "meta": {
    "do": [
      {"call": {"fn": "truncate_sentences", "args": {"text": "@draft_text", "range": "@sentence_range"}, "to": "$final"}},
      {"save": {"@final_text": "$final"}},
      {"outcome": "pass"}
    ]
  }
}
```

### Audit

```json
{
  "element_id": "audit",
  "handler": "__dsl__",
  "meta": {
    "do": [
      {"claims": "$fails"},
      {"if": {
        "test": {"empty": "$fails"},
        "then": [
          {"set": {"@audit_status": "pass"}},
          {"return": "@final_text"},
          {"outcome": "done"}
        ],
        "else": [
          {"set": {"@audit_status": "fail"}},
          {"return": "@final_text"},
          {"outcome": "done"}
        ]
      }}
    ]
  }
}
```

### Global Check

```json
{
  "element_id": "global_check",
  "handler": "__dsl__",
  "transitions": {"fail": "repair_global", "pass": "done"},
  "meta": {
    "do": [
      {"claims": {"scope": "tree", "to": "$global_failures"}},
      {"save": {"@global_failures": "$global_failures"}},
      {"if": {
        "test": {"empty": "$global_failures"},
        "then": [{"outcome": "pass"}],
        "else": [{"outcome": "fail"}]
      }}
    ]
  }
}
```

### Run Children

```json
{
  "element_id": "run_children",
  "handler": "__dsl__",
  "meta": {
    "do": [
      {"for_each": {
        "in": "@child_ids",
        "as": "$child_id",
        "do": [
          {"run_node": {"node_id": "$child_id", "to": "$record"}}
        ]
      }},
      {"outcome": "pass"}
    ]
  }
}
```

---

## Planning Rules

When converting natural language into a tree:

1. **Extract outputs** — what concrete items need to be produced?
2. **Create one child node per output unit** — each node is a self-contained task.
3. **Put shared constraints into `global_claims`** — e.g. uniqueness across items.
4. **Put per-item constraints into node `claims`** — e.g. sentence range, required details.
5. **Use DSL elements** for: generation → check → repair → compress → audit.
6. **Use root node** to: run children and handle global checks if needed.
7. **Set `global_meta`** with: `language`, `sentence_range`, `temperature`, `creative_agent`.
8. **Prompts in templates** — never hardcode prompts, use `render` + `{$@field}` substitution.
9. **Claims prefer DSL** — use `evaluator: "__dsl__"` with `meta.dsl` predicates.

## Worker Rules

The worker should:
- emit valid JSON only
- prefer DSL over custom handler names
- prefer template fields over hardcoded text
- keep node structure explicit
- keep claims explicit with DSL predicates
- keep transitions explicit
- use `@@creative_agent` for LLM calls (configurable)

The worker should not:
- emit Python code
- invent unavailable runtime functions
- mix prose with JSON output
- rely on hidden state outside `data`, `global_meta`, `bindings`, `claims`, `meta`
- hardcode agent names (use `@@creative_agent` ref)
