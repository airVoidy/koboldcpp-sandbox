# Session Summary — 2026-03-25

## What We Built
Reactive Task Builder — YAML DSL workflow engine with Slack-like threaded UI,
connected to KoboldCpp LLM workers and ComfyUI image generation.

## Architecture
- **Server**: Python/FastAPI (`server.py`, `workflow_dsl.py`) — executes YAML workflow, proxies LLM calls
- **Client**: Single HTML (`reactive_chat.html`) — tree UI, threads, discussions, admin mode
- **Workers**: KoboldCpp instances (local:5001 generator, remote:5050 analyzer)
- **ComfyUI**: http://127.0.0.1:8188 — image generation via workflow JSON

## Key DSL Features
- `probe_continue` — KV-cache optimized 1-token extraction via think injection
- `grammar` — GBNF constraints for guaranteed output format
- `table-as-query` — inject answer in think, start markdown table header, model fills rows
  - Replaces separate table/trim/verify calls with ONE continue
  - Entities + axioms + line numbers in single table
  - Transposed table for cross-verification
- `verify_axioms` — step-by-step verification via `((claim) == 1) ===` in think
- `comfyui` — queue prompts to ComfyUI, poll for completion, show images
- `triggers` — manual actions (check, generate) callable from UI buttons

## UI Features
- **Tree nodes**: collapsible, with tags, RESULT code block, reactions
- **Thread**: workflow log (claims, table, trim, verify messages)
- **Discussion**: separate chat under entities with serialized tree context
- **Reply sub-threads**: depth-1 replies on any message (forum-style)
- **Admin Mode**: right-click context menu for edit/delete/add on tags, list items, messages
- **Structured items**: `{text, author, policy, ts}` format for all lists
- **LocalStorage**: state persistence across page refresh
- **Clear**: server-side KV cache reset + client reset
- **Stop All**: abort JS fetches + KoboldCpp `/api/extra/abort`

## Key Discoveries
1. **Table-as-query**: One continue with header = entities + axioms + line numbers.
   Replaces ~15 sequential calls.
2. **Transposed verification**: Fill table → transpose → fill again → compare.
   100% consistency check.
3. **probe_continue**: Think injection + stop tokens + grammar = 1-token extraction.
   Model-specific optimization (qwen_fastpath profile).
4. **Grammar + continue**: Works in KoboldCpp with proper UTF-8 encoding.
   `grammar + stop` conflicts, but grammar alone handles termination.
5. **KV cache as state**: Workers remember context. Clear = reset KV cache on all workers.

## Files
- `tools/reactive_chat.html` — main UI (3000+ lines)
- `src/kobold_sandbox/workflow_dsl.py` — YAML interpreter + builtins
- `src/kobold_sandbox/server.py` — FastAPI server
- `examples/behavior_case/demo_workflow.yaml` — canonical workflow
- `examples/behavior_case/WORKFLOW_DSL_SPEC.md` — DSL specification

## What's Next
- **Atomic Tasks page** — playground for table-as-query experiments
- **ACL system** — NTFS-style permissions with groups, inheritance per node
- **`/api/state/patch`** — unified mutation API with policy checks
- **Table-as-query DSL step** — replace separate table/trim/verify with one continue
- **Discussion → worker auto-reply** improvements
- **ComfyUI image display** in entity nodes (not just thread)

## Important Rules (learned the hard way)
1. Don't touch working code without asking
2. Don't add hardcoded prompts — everything in DSL or UI
3. Don't add `if/when` to DSL — use tags/reactions/triggers instead
4. Don't strip errors silently — show everything in UI
5. Server is stateless — state lives in KV cache (workers) and localStorage (client)
6. Clear = server-side function, not client-side
7. Always check encoding when writing files with Russian text
8. probe_continue prompts are tuned — `===` not `==`, specific format matters
