# Runtime Containers

## Three-Layer Architecture

```
Source data (pchat/) -> Runtime containers (runtime/containers/) -> Sandboxes (runtime/sandboxes/)
```

## Container _meta.json

Declarative manifest:
- **resolve**: how to find source data (source_root or source_template with interpolation)
- **actions**: available commands with state_path, target_template, rebuild_containers
- **depends_on**: other containers this one reads from
- **selected_from**: where selection state comes from

## Materialize

Reads source data, builds resolved object, flattens to rows (flatten_json), writes sandbox files.
Triggered by rebuild_containers on any action.

## Current Containers

- **channels_selector**: lists channels, tracks selected channel
- **current_channel**: shows messages for selected channel, depends on channels_selector
