# Architecture Overview

## Core Principles

- **FS-first**: Nodes = real directories with _meta.json + _data.json
- **Server-side logic**: Python server handles all transforms, JS is display layer only
- **CMD as universal wrapper**: Every action is a CMD object with validation, context, composability
- **Template inheritance**: card (base) -> cards (container) -> channel, message etc.
- **Reactive containers**: Runtime containers with state, resolve, rebuild_containers

## Layers

- **L0**: Message stack (FIFO per container, patches as messages)
- **L1**: CMD dispatch (template commands .py with hot-reload)
- **L2**: Pipeline orchestration (CMD chains, verify loops)

## Key Directories

- `root/templates/` — type definitions (schema.json + commands/*.py + views/)
- `root/runtime/containers/` — runtime state (_meta.json + state.json + cmd_log.jsonl)
- `root/runtime/sandboxes/` — materialized views (resolved.json, rows.json)
- `root/pchat/` — source data (channels, messages)
- `root/wiki/` — project wiki (this)
