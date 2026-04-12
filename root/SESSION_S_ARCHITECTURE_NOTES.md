# Session S Architecture Notes (2026-04-12)

## 1. L0/L1/L2 Layer Model

- **L0** = pure FS tree. Each node = folder with own exec queue. L0 doesn't care about JSON content. Stores tree as flat list, tree shape matters for policy/traversal/parallelization.
- **L1** = data layer: field resolution, projections, patches. Fields as runtime singletons by canonical path.
- **L2** = serialized views: lists, tables, cards, trees. Projection output for rendering.

## 2. Node Invariants

- Node = any Python object that serializes to JSON without loss.
- Two hard rules: (1) unique name per scope, (2) valid JSON serialization.
- Node may have server-side fields with plain keys.
- Unlimited children of any type (hypergraph-capable).
- `{type}_{id}` naming: type without index = template root (occupies [0]), instances start from [1].

## 3. Scope Visibility

- Parent node CANNOT read or watch children. Its data belongs to upper scope.
- Children CAN read parent/root (visibility up, not down).
- Exec queue: FIFO, server processes from tail to 0. Current = always [0], fog of war below.
- Select = choosing which exec scope to write to.

## 4. Source of Truth

- Immutable exec log = L0 truth. `_meta.json`/`_data.json` = cache/snapshot.
- Apply patch = revision switch, not data overwrite. New revision = new exec entry.
- Undo: client = pop exec log (one step back). Server = revert (new entry with old value).
- All mutations = exec entries. Only server can apply patch on canonical values.

## 5. Runtime Objects

- Live in memory, not on disk. FS serialization = lazy/debug.
- `_write_data` = runtime snapshot dump, not truth mutation.
- FS tab in pipeline-chat = virtual FS showing runtime objects from memory.
- Only real writes: append to exec log (`_exec.jsonl`, `_children.jsonl`).

## 6. Field Model

- Canonical atom = Field = `{path, value}` pair. Bidirectional link.
- `path ↔ value` = atomic runtime data object (row).
- Fields are self-standing objects outside tables.
- Virtual tables = projections over fields, not source of truth.
- Flat 1D list of `{path, value}` pairs = universal primitive. Everything else = projections.

## 7. Projection Model

- Projection = resolve(FS_state) → Raw view. One pass, zero writes.
- Compiled state = frozen projection snapshot = ready-to-render.
- New exec entry → incremental patch to snapshot → new projection.
- Batch accumulator: lambdas unfold, commands accumulate, one apply when complete.
- Even "heavy" structure changes = one patch on projection level.

## 8. Bind Model

- Bind = lambda wrapper with explicit invocation. NOT a static link.
- Can be placed on non-existent fields, fires when field appears.
- On mutation of projection field → bind resolves canonical path → propagates patch to source.
- One-shot (fire once on appear) or per-action (fire on each change).
- In serialization: "bind" field = back-reference to canonical source for write-through.
- Bind at projection creation level, not at object level.
- Batch of binds = batch of one-step projections assembled at once.

## 9. Template System

- `msg` (no index) = template root, symlinked into each node where needed.
- Instances `msg_1`, `msg_2` start from 1 (template occupies [0]).
- Local template patch = `msg_0/` folder with revision, activate/deactivate by toggling one field.
- Template inheritance by nesting depth: root → channel-level (patched) → children inherit.
- Template = source of rules + bind declarations.
- `card` / `cards` = root types = `{}` and `[]` wrappers. Intersection of client and server contracts.

## 10. Exec-as-Capability

- No exec declaration on node → no operations possible.
- Exec exists but no children[] → read-only (can patch own fields, cannot create nested).
- Exec + children[] + append(type[]) declared → can post that type.
- `append(channel.children[], msg[])` = both bind AND policy ("this channel accepts messages").

## 11. List-Scope Invariant

- Every by-type collection MUST have virtual list wrapper: `channel.children[].msg[]`.
- Post goes to `msg[]`, not to channel. Channel doesn't need to know.
- Projection binds `msg[]` back to `channel.children` via append.
- No scope routing needed for post. Write directly to typed container.

## 12. Shadow Slots / ApplyShadowPatch

- Shadow slot = virtual projection of a cell that doesn't exist yet.
- Lambda-bind on empty field, materializes only when not-null.
- `channel.children[] = {msg[] +#reactions}` — shadow-extend template.
- Push reactions into type list, append slots to messages only when non-null.

## 13. Client Field Model

- `self.projection` = field name (not value). `self[self.projection]` = resolved on render.
- Switching projection = changing one string, entire render updates reactively.
- Container-level selector switches projection for all children at once.
- Projected field = lambda wrapper over source field.
- Patch projected.value → proposed to source, but only source can ApplyPatch.
- Field projections = 1-to-many relation by value: `value.($value)`, `cmd.($cmd)`.

## 14. Patch Flow

- Exec(baked_script, selector_value) → resolve new state → diff → patch.
- Resolve happens BEFORE patch formulation.
- One field mutation → one rows() object change → one patch.
- Apply patch on source of truth = one atomic batch with all affected canonical fields.

## 15. Sandbox vs Server

- Server L0: node tree + exec queue. Thin. Doesn't know about representations.
- Client: projection consumer. Thin. Only reads resolved data.
- Sandbox: thick. All three passes, shadow objects, checkpoint cache, runtime objects.
- Sandbox FS as interface: flexible, visual, assemble by hand then serialize and send.
- User sandbox = full local exec permissions, server doesn't see sandbox data.
- Data transfer: only through exec interface.

## 16. Three Linear Passes (Shadow Meta-Object Compilation)

1. Expand virtual FS in all directions with max-overloaded case (all components, all commands, even impossible combos). Fill all slots with all types.
2. Walk templates: collect nested shadow types, all revisions, all transforms into one shadow object.
3. Collapse all paths to unit length: from any Field to any state = one transform.

Result: complete routing table `server_repr ↔ client_repr` for all slots.
- New type = new endpoint = new link in shadow. One pass to resolve.
- Flood fill over endpoint graph: find shortest route to needed state.
- O(N) by field count, one pass, no recursion.

## 17. Atomic Path Representation

- Flat JSON representation until payload/list element.
- Each nested object/list → flatten to Flat Object. Atomic canonical path inside cells.
- Payload unfolds into runtime object via `{payload}.data` / `[payload].data` resolver.
- Server nodes = same pattern: folder name → path, contents → data.
- Relative path from nearest checkpoint-parent for serialization. Canonical = from root.
- `{_meta.json ↔ jsonObj(_meta)}` = portal link, paths inside = relative from `{_meta}`.

## 18. Ecosystem Decisions

- React/TSX for prototyping (hot-reload, types, component reuse). Vanilla DOM for production (baked from React).
- JSONata as embedded transform/query engine (same lib on server Python + client JS).
- KoboldCPP tool calling (tested, works without --jinjatools).
- Structured Output: three mechanisms (GBNF, tool calling, JSON Schema constrained decoding).
- Packages: cmdk, rjsf, ahooks, CopilotKit patterns, LiteLLM, LangChain/LangGraph, DuckDB, Refine, GraphQL.

## 19. Implementation Done This Session

- Wiki CMD (/wiki init/status/ingest/write/read/rm/index)
- prompt-pal local fork (KoboldCPP tool calling)
- TSX pipeline-chat client (React 19, Vite 5, Tailwind 4)
- DebugConsole: L0 Log, Shell, Objects, FS View, Inspector, Projection, JSONata tabs
- Client CMD resolver with optimistic updates
- Assembly DSL interpreter (mirrors Python)
- JSONata query layer with runtime bindings
- useFieldRef hook with display facet switching
- Sandbox runtime (exec-first, runtime objects in memory)
- Exec-as-capability enforcement in template schemas
- Patch-only protocol with `since` parameter
- Endpoint logging with per-endpoint JSONL
- PR #20 on GitHub
