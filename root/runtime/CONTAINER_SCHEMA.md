# Container Schema

Runtime container = explicit filesystem object that stores local state, action rules, and a materialized sandbox view over source nodes.

Layout:

```text
root/runtime/containers/<container_id>/
  _meta.json
  state.json
  cmd_log.jsonl
```

Materialized output:

```text
root/runtime/sandboxes/<container_id>/
  _meta.json
  resolved.json
  rows.json
  source_refs.json
```

Minimal `_meta.json` fields:

- `id`: stable container id.
- `kind`: runtime object kind. Current runtime uses `container`.
- `resolve`: how materialize finds source data.

Useful optional fields:

- `state_schema`: expected local state shape.
- `depends_on`: other containers this one derives state from.
- `selected_from`: where current selection comes from.
- `action_defaults`: defaults merged into each action.
- `actions`: declarative action specs.

`resolve` fields understood now:

- `source_root`: source directory relative to `root/`.
- `source_template`: source path template with `{containers.<id>.state.<path>}` interpolation.
- `children`: currently `none` or `direct`.

`actions.<name>` fields understood now:

- `state_path`: dot-path inside `state.json` to mutate.
- `target_template`: source node path template for mutations.
- `rebuild_containers`: list of containers to rebuild after action.
- `select_new`: for create flows, whether to write the new id into selection state.

Guidelines:

- Keep source-of-truth in source nodes, not in container state.
- Use container state only for local runtime context such as `selected`.
- Prefer explicit `depends_on`, `selected_from`, and `rebuild_containers` over hidden Python coupling.
- If behavior cannot be explained by reading `_meta.json`, it is still too implicit.
