# LLM Integration

## KoboldCPP

Local LLM server, OpenAI-compatible API at localhost:5001.

### Three structured output mechanisms

1. **GBNF grammars** — token-level constraints (used in verify/probes)
2. **Tool calling** — /v1/chat/completions with tools + tool_choice (tested with Qwen3.5-9B)
3. **JSON Schema constrained decoding** — guaranteed schema conformance

### Two-stage pattern

1. **Decision stage**: LLM sees tool names + descriptions, picks one (light context)
2. **Parameter stage**: full schema for chosen tool only (SO constraint)

## Think Injection

Structured prompting via stop/continue tokens. Near-instant on KV cache.
Used for multi-step reasoning without multiple API calls.
