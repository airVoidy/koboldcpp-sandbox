# Memory

## Me
vAiry — developer building a local agentic sandbox over KoboldCPP. Deep technical expertise, thinks architecturally, prefers concise action-oriented communication in Russian/English mix.

## Stack
| Layer | Tech |
|-------|------|
| LLM | KoboldCPP (Qwen3.5-9B), local, OpenAI-compatible API |
| Server | Python 3.11+, FastAPI, uvicorn |
| Client | Vanilla HTML/JS (migrating toward TSX) |
| Storage | FS-first (directories + _meta.json + _data.json), git versioning |
| Wiki | FS-based (root/wiki/), auto-index, ingest |

## Key Concepts
| Term | Meaning |
|------|---------|
| CMD | Typed command container — op + context + validation + composability |
| ConsoleScope | Named terminal instance (own cwd, log, redo) |
| Template command | .py file in templates/{type}/commands/, hot-reload by mtime |
| Container | Runtime object with state, actions, resolve, rebuild_containers |
| Materialize | Build resolved view from source data + container state |
| Think injection | Structured prompting via stop/continue, near-instant on KV cache |
| GBNF | Grammar constraints for structured LLM output |
| Bake | Freeze CMD sequence or node structure into reusable template/pipeline |
| Flat rows | flatten_json output — dot-path addressable 2D table |

## Architecture Rules
- Server-side logic only, JS = display layer
- No hidden LLM calls — all visible in UI
- No hidden system prompts — ChatML instruct
- Don't edit LLM prompts beyond what was explicitly requested
- Never filter LLM output format silently
- Workers parallel, listeners react on data arrival
- DataStore must be scoped (run/node), not flat global
- No heredoc in git commits on Windows

## Projects
| Name | What |
|------|------|
| Pipeline Chat | Slack-like chat with CMD commands, containers, reactions |
| Atomic Wiki | FS + API wiki with git versioning |
| Atomic DSL | Ingest/patch/resolve cycle, flat table view |
| prompt-pal | Example React app, local fork using KoboldCPP tool calling |

## Preferences
- Warm casual tone, concise
- Russian for discussion, English for code/docs
- Don't rush — think before implementing
- Prefer simple generic solutions over complex specific ones
