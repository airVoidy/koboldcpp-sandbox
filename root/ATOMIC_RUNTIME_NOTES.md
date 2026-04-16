# Atomic Runtime Notes

Current working model:

- Canonical runtime atom is `Field`.
- `Field.id` is the canonical atomic-dsl path.
- Canonical fields are runtime singletons by path.
- `bind` is wiring only at the DSL level.
- Runtime may compile binds into lambda/exec wrappers internally.
- Projection objects may also define local `rule` fields over bound fields.
- Generic projection rules are appended as exec-like rule objects and materialized by `op`.
- Projection `op` handlers should live in `templates/root/runtime/projection-ops/`, not as server-specific branches.
- Table/matrix transforms should follow the same pattern via `templates/root/runtime/table-ops/`.
- Initial table ops can stay simple: add row, sort rows, filter rows; richer matrix sugar can layer on top.
- Range/slice should also live at table-op level so long lists can be paged without special server endpoints.
- A table can also be populated from direct FS children via modular table-op, instead of adding rows one by one.
- A table can also be populated from append-only child-log refs, so long message lists do not need full directory scans.
- Child-log based loading should support cursor-like ref windows (`before_ref` / `after_ref`) in addition to raw offsets.
- Table containers may keep pagination/window state locally and feed it into autoload ops at materialize time.
- Views and virtual tables are projections over fields, not source of truth.
- `value` in view cells is resolved cache.
- `atomic_path` is legacy-compatible naming; `bind` is the preferred view-level key.

Path model:

- Canonical paths stay stable.
- Local paths belong to projection/view scope.
- Projection objects are siblings of canonical objects in runtime, not replacements.

Payload/file scope conventions under discussion:

- `obj.(_data.json).content` loads object payload scope, then resolves local path.
- `obj.[_data.jsonl].0.ref` loads list/jsonl payload scope, then resolves an item.
- Payloads may auto-expand into flat field lists for runtime work.

Node model:

- A node is a container of local exec/messages/patches.
- Resolved state is a projection, not the source of truth.
- Message-like objects are better treated as slot-nodes with local exec history.

Persistence model:

- Keep `_meta.json` and `_data.json` as current materialized snapshot/cache.
- Keep append-only exec/patch history separate (currently `_exec.jsonl` is the intended direction).
- Checkpoints/snapshots are optimizations, not source of truth.

Near-term implementation steps:

1. Replace view-level thinking from `atomic_path` to `bind`.
2. Add field-definition primitives (`define_field` / `ensure_field`) for empty canonical fields.
3. Move virtual-table cells toward field refs plus local rules.
4. Evolve message state toward slot-log + resolved projection.
