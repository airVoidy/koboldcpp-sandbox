# Context Summary — Behavior Orchestrator + DSL + Verifier

## Architecture

### Core Files
| File | Purpose |
|---|---|
| `src/kobold_sandbox/behavior_orchestrator.py` | BehaviorNode, BehaviorTree, BehaviorOrchestrator, LLMBackend, ElementExecutionResult, Claims |
| `src/kobold_sandbox/dsl_interpreter.py` | DSL v2 interpreter: $x=local, @x=node.data, @@x=global_meta. Handles: set, save, render, call, if, for_each, run_node, claims, outcome, return, copy, append, collect |
| `src/kobold_sandbox/nl_to_dsl.py` | NL-to-DSL pipeline: plan_items(), generate_element_do(), build_tree_from_plan(), edit_tree_via_chat() (patch-based), apply_set_patches() |
| `src/kobold_sandbox/logic_manifest.py` | Atomic sieve verifier: parse manifests, verify_logic() with cascading sieve (axiom/confirmed/hypothesis/declined) |
| `src/kobold_sandbox/server.py` | FastAPI: /api/behavior/* (tree CRUD, plan, run, agents, NL edit), /api/logic/verify, /chat, /behavior HTML |
| `tools/behavior_tree.html` | Behavior tree UI: node list, element flow editor, claims, data, JSON modal, NL chat edit, agent config, namespace reference, live polling |
| `tools/multi_agent_chat.html` | Multi-agent chat: SSE streaming, think interceptor, worker no-think toggle, TTS, task lists |
| `examples/behavior_case/NL_TO_BEHAVIOR_DSL_SPEC.md` | DSL v2 specification for LLM context |

### LLM Endpoints
- `http://192.168.1.15:5050` — 27B agent (planner/creative, registered as `qwen_27b_planner`)
- `http://localhost:5001` — small worker (registered as `small_context_worker`)
- Agent names `small_context_worker` and `qwen_27b_planner` are hardcoded in several places — needs cleanup

### Server
- `kobold-sandbox serve --host 127.0.0.1 --port 8060`
- DataStore API mounted at `/api/datastore/`
- Behavior API at `/api/behavior/`
- Logic verifier at `/api/logic/verify`

## DSL v2 Namespace
```
$x   — local variable (element execution scope)
@x   — node.data.x
@@x  — tree.global_meta.x
#x   — claim/element reference (future)
```

## DSL Commands
```json
{"set": {"@status": "pending", "$count": 0}}
{"save": {"@draft_text": "$text"}}
{"copy": {"from": "@draft_text", "to": "@final_text"}}
{"render": {"to": "$prompt", "template": "Style: {$@style}. Hair: {$@hair_color}."}}
{"call": {"fn": "call_agent", "args": {"prompt": "$prompt"}, "to": "$text"}}
{"claims": "$failures"}
{"if": {"test": {"empty": "$failures"}, "then": [...], "else": [...]}}
{"for_each": {"in": "@child_ids", "as": "$child_id", "do": [...]}}
{"run_node": {"node_id": "$child_id"}}
{"outcome": "pass"}
{"return": "@final_text"}
```

## Pipeline Flow
1. `plan_items()` — 1 LLM call: NL task → JSON array of items
2. `_generate_pipeline()` — 1 LLM call: generates shared element flow (check/repair/finalize)
3. `generate_element_do()` × N — per-item draft element
4. `build_tree_from_plan()` — assembles BehaviorTree from plan + pipeline + items

## LLMBackend.call() — Continue Fix
- **no_think**: assistant prefill `<think>\n\n</think>\n\n` + `continue_assistant_turn: true` on FIRST request (same as multi_agent_chat.html Generate More)
- **Continue loop**: max_continue=20, sends full_assistant content for KV cache match
- **finish_reason**: read from OAI `/v1/chat/completions` response directly (not from KoboldClient wrapper which strips it)

## NL Edit — Patch-based
- Model returns `[{"set_path": "nodes.item-01.data.hair_color", "value": "red"}]`
- `apply_set_patches()` applies them with error handling
- Failed patches → retry with error messages + valid paths hint
- Element-level edit: full JSON replacement (small enough)
- Tree/node-level edit: patch-based (too large for full replacement)

## Known Issues / TODO

### CRITICAL: Model generates invalid JSON separator
- Small model (localhost:5001) consistently generates `},{"{"id"` instead of `},{"id"` between JSON array objects
- This is a MODEL behavior, not a continue bug
- JSON Repair regex partially handles it but not reliably
- **Fix needed**: better few-shot examples in PLAN_SYSTEM prompt, or switch to 27B for planning, or structured output format

### Hardcoded agent names
- `small_context_worker` and `qwen_27b_planner` hardcoded in:
  - `nl_to_dsl.py` (default agent_name params)
  - `behavior_orchestrator.py` (create_reference_behavior_orchestrator)
  - `server.py` (fallback agent selection)
- Should be fully dynamic from UI agent config

### Reference tree still loaded on startup
- `build_character_description_reference_tree()` creates "description" themed tree on server start
- Should be empty or loaded from saved state

### Element flow hardcoded in build_tree_from_plan
- `_generate_pipeline()` generates shared elements via LLM (1 call)
- Per-item draft generated via LLM
- But `element_specs` descriptions are still semi-hardcoded
- Goal: fully LLM-driven pipeline generation

### DSL interpreter missing ops
- `increment` (`{"set": {"@x": {"inc": "@x"}}}`) — may not be implemented
- `truncate_sentences` as DSL op — partial
- Claim DSL evaluation — partial

## Verifier (logic_manifest.py)
- Cascading sieve: axioms filter worlds, then each hypothesis checked
- Statuses: `accepted` (axiom, always applied), `confirmed` (follows from axioms), `hypothesis` (narrows but valid), `declined` (0 worlds)
- `verify_logic()` auto-detects Einstein puzzle vs generic
- `/api/logic/verify` endpoint accepts raw_schema in multiple formats (ENTITIES/AXIOMS/HYPOTHESES, ENTITIES/RULES/BRANCHES, ATOMIC_RULES)

## Tests
- `tests/test_behavior_orchestrator.py` — 6 tests
- `tests/test_behavior_api.py` — 4 tests
- `tests/test_dsl_interpreter.py` — DSL command tests
- `tests/test_logic_manifest.py` — atomic sieve tests (4 etalon tests)
- Run: `python -m pytest tests/ -q`

## Data
- `data/behavior_runs/` — dumped tree JSON from successful runs
- `examples/behavior_case/character_description_reference_tree.json` — reference tree template
