# Starter for next chat

Read these files for context:
@C:\llm\KoboldCPP agentic sandbox\docs\SESSION_SUMMARY_2026_03_25_B.md

We're building Atomic Tasks — a creator mode page in Reactive Task Builder.
Server-side framework: JS is display only, all tools go through `/api/atomic/run` and `/api/atomic/scope`.

## Immediate TODOs:

1. **Global Params UI buttons**: + Table, + Text Area, + Key:Value Param (currently only + param exists)
2. **@config.input** — store task text in Global Params config, not as manual entity
3. **@config.prompt_claims** — prompt template in config with `@input` reference
4. **Resolved preview** — show @ref substitution result in entity card (collapsed "▸ resolved" section)
5. **Wire client scope to server** — scope_begin/scope_end → single `/api/atomic/scope` call

## Design Decisions:
- No hardcoded prompts — everything in config or user entities
- `@ref` syntax everywhere — prompts, messages, tools
- Scope = batch execution, local vars, compose export
- Triggers: `on @dep: action` — reactive, not sequential
- All LLM params visible in UI

## Server: `python -m uvicorn kobold_sandbox.server:app --host 0.0.0.0 --port 5002`
## Workers: local:5001 (generator), remote:5050 (analyzer)
