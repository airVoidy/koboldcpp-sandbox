# Starter message for next chat

Copy-paste this as your first message:

---

Read these files for context:
@C:\llm\KoboldCPP agentic sandbox\docs\SESSION_SUMMARY_2026_03_25.md
@C:\llm\KoboldCPP agentic sandbox\examples\behavior_case\WORKFLOW_DSL_SPEC.md
@C:\llm\KoboldCPP agentic sandbox\examples\behavior_case\demo_workflow.yaml

We're building a Reactive Task Builder with YAML DSL workflow engine.
Repo: https://github.com/airVoidy/koboldcpp-sandbox

Key discovery from last session: **table-as-query** — inject answer in `<think>`, close think, start markdown table with column headers (entities + axioms + line numbers), model fills all rows in ONE continue call. Replaces ~15 separate calls.

Transposed verification works: fill table → transpose columns/rows → fill again → compare = 100% consistency check.

Next task: **Add Atomic Tasks page** — a playground/UI for experimenting with:
1. Table-as-query (define columns, inject content, model fills)
2. Transposed verification (auto cross-check)
3. Structured item DB with `{text, author, policy, ts}` format
4. ACL-style permissions (NTFS-like groups with node-level override)
5. `/api/state/patch` unified mutation API

Important rules:
- Don't add hardcoded prompts — everything in DSL/UI
- Don't add if/when to DSL — use tags/reactions/triggers
- Don't touch working code without asking
- Show all errors in UI, never strip silently
- Check encoding when writing Russian text
- `===` not `==` in verify prompts (tuned format)

Server: `python -m uvicorn kobold_sandbox.server:app --host 0.0.0.0 --port 5002`
Workers: local:5001 (generator), remote:5050 (analyzer)
ComfyUI: http://127.0.0.1:8188
