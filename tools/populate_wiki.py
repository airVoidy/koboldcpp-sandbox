"""Populate project wiki with pages."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import importlib.util

spec = importlib.util.spec_from_file_location(
    "wiki", str(Path(__file__).resolve().parents[1] / "root" / "templates" / "root" / "commands" / "wiki.py")
)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class WS:
    def __init__(self):
        self.root = Path(__file__).resolve().parents[1] / "root"


ws = WS()
wiki_pages = ws.root / "wiki" / "pages"

pages = {
    "architecture": "# Architecture Overview\n\n## Core Principles\n\n- **FS-first**: Nodes = real directories with _meta.json + _data.json\n- **Server-side logic**: Python server handles all transforms, JS is display layer only\n- **CMD as universal wrapper**: Every action is a CMD object with validation, context, composability\n- **Template inheritance**: card (base) -> cards (container) -> channel, message etc.\n- **Reactive containers**: Runtime containers with state, resolve, rebuild_containers\n\n## Layers\n\n- **L0**: Message stack (FIFO per container, patches as messages)\n- **L1**: CMD dispatch (template commands .py with hot-reload)\n- **L2**: Pipeline orchestration (CMD chains, verify loops)\n\n## Key Directories\n\n- `root/templates/` \u2014 type definitions (schema.json + commands/*.py + views/)\n- `root/runtime/containers/` \u2014 runtime state (_meta.json + state.json + cmd_log.jsonl)\n- `root/runtime/sandboxes/` \u2014 materialized views (resolved.json, rows.json)\n- `root/pchat/` \u2014 source data (channels, messages)\n- `root/wiki/` \u2014 project wiki (this)\n",

    "cmd-system": "# CMD System\n\n## What is CMD\n\nCMD = typed container with logic. Not just a command call, but an object carrying:\n- **op**: what to do\n- **input**: what was passed\n- **user**: who\n- **scope**: which terminal\n- **context**: arbitrary fields via dot-notation\n\n## Template Commands\n\nPython files in `root/templates/{type}/commands/{name}.py`\n\nSignature: `def execute(args, user, scope, ws) -> dict`\n\nResolution: current node type -> schema.inherits -> ... -> None\n\nHot-reload: mtime-based, cached in memory\n\n## Generic Strategies\n\n| Strategy | What it does | Example |\n|---|---|---|\n| set | write value | edit message content |\n| toggle | exists->remove, not->add | reaction by author |\n| increment | counter++ | reaction count |\n| find_or_create | find by key or create slot | reaction emoji slot |\n| append | add to end of list | post message |\n\n## ConsoleScope\n\nNamed terminal instances with own cwd, log, redo stack.\n- `CMD` scope for user actions\n- `channel:*` for channels\n- `agent:*` for agents\n",

    "containers": "# Runtime Containers\n\n## Three-Layer Architecture\n\n```\nSource data (pchat/) -> Runtime containers (runtime/containers/) -> Sandboxes (runtime/sandboxes/)\n```\n\n## Container _meta.json\n\nDeclarative manifest:\n- **resolve**: how to find source data (source_root or source_template with interpolation)\n- **actions**: available commands with state_path, target_template, rebuild_containers\n- **depends_on**: other containers this one reads from\n- **selected_from**: where selection state comes from\n\n## Materialize\n\nReads source data, builds resolved object, flattens to rows (flatten_json), writes sandbox files.\nTriggered by rebuild_containers on any action.\n\n## Current Containers\n\n- **channels_selector**: lists channels, tracks selected channel\n- **current_channel**: shows messages for selected channel, depends on channels_selector\n",

    "llm-integration": "# LLM Integration\n\n## KoboldCPP\n\nLocal LLM server, OpenAI-compatible API at localhost:5001.\n\n### Three structured output mechanisms\n\n1. **GBNF grammars** \u2014 token-level constraints (used in verify/probes)\n2. **Tool calling** \u2014 /v1/chat/completions with tools + tool_choice (tested with Qwen3.5-9B)\n3. **JSON Schema constrained decoding** \u2014 guaranteed schema conformance\n\n### Two-stage pattern\n\n1. **Decision stage**: LLM sees tool names + descriptions, picks one (light context)\n2. **Parameter stage**: full schema for chosen tool only (SO constraint)\n\n## Think Injection\n\nStructured prompting via stop/continue tokens. Near-instant on KV cache.\nUsed for multi-step reasoning without multiple API calls.\n",

    "ecosystem": "# Ecosystem & Dependencies\n\n## Planned Client Stack (TypeScript/React)\n\n- **shadcn/ui** \u2014 component library\n- **cmdk** \u2014 command palette (maps to CMD architecture)\n- **rjsf** \u2014 schema.json -> auto-generated forms\n- **ahooks** \u2014 utility hooks (virtual lists, requests, websockets)\n- **CopilotKit** patterns \u2014 agent-UI shared state, generative UI\n\n## Server/LLM\n\n- **LiteLLM** \u2014 unified LLM proxy, scheduling, tool wrappers, dashboard\n- **LangChain/LangGraph** \u2014 dynamic tools, graph orchestration, pipeline visualization\n- **DuckDB** \u2014 in-process analytical DB, SQL over JSON/flatten_json rows\n\n## Data/Admin UI\n\n- **Refine** \u2014 headless React CRUD framework with custom data providers\n- **GraphQL** \u2014 typed query layer over FS tree\n\n## Protocols\n\n- **gRPC + protobuf** \u2014 typed binary protocol for server-to-server\n",

    "pipeline-chat": "# Pipeline Chat\n\n## Overview\n\nSlack-like chat interface at /pipeline-chat. Channels with messages, reactions, user scopes.\n\n## How It Works\n\n1. Client sends CMD via `/api/pchat/exec` (e.g. `/cpost hello`)\n2. Server resolves template command, executes in scope\n3. Container state updated, rebuild_containers triggered\n4. Client receives materialized view\n\n## Panels\n\nLoaded from template views at runtime:\n- `channels/views/sidebar.html` + `sidebar.js` \u2014 channel list\n- `channel/views/content.html` + `content.js` \u2014 messages\n- `message/views/compact.html` \u2014 message card template\n\n## Key Commands\n\n`/cselect`, `/cpost`, `/cmkchannel`, `/cpatch`, `/cedit`, `/cdelete`, `/creact`\n\nAll route through container system with automatic rebuild.\n",
}

for slug, content in pages.items():
    (wiki_pages / f"{slug}.md").write_text(content, encoding="utf-8")
    print(f"wrote {slug}.md")

# Rebuild index
r = mod.execute(["index"], "claude", None, ws)
print(f"index rebuilt: {r['pages']} pages, {r['sources']} sources")

# Status
import json
print(json.dumps(mod.execute(["status"], "claude", None, ws), indent=2))
