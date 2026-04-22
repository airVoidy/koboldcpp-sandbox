# Atomic Object — Universal Runtime Wrapper v0.1

## Purpose

Fix the universal wrapper over any runtime object. The pattern is **already implemented** in `wip/atom_prototype/` — this doc names the primitives, explains how they compose, and lays the migration path from `koboldcpp-sandbox/src/data/{VirtualObject, VirtualList}` to them.

The slogan (from `C:\llm\atom-prototype-backup-2026-04-18\SESSION_SUMMARY.md` §1):

> **Atoms are MOV-wrapped references. Same operational structure across sizes; only payload differs. Identity by content hash.**

Corollary: **any object can be wrapped into an atom**. `VirtualObject`, `VirtualList`, a Lexical node, a Jupyter cell, a LangExtract span — all are instances of the same wrapper with different payload.

---

## The Canonical Wrapper

**`VirtualTypeEntry`** — `wip/atom_prototype/src/namescope.ts:44-49`:

```ts
export type Hash = string

export interface VirtualTypeEntry {
  hash: Hash            // content-hash identity
  type: string          // "what kind of thing"
  payload: unknown      // ← any structure
  tags?: string[]       // free-form markers
}
```

Four fields. `payload: unknown` — the wrapper commits to nothing about shape. Everything else is registry + overlays.

**Why four fields are enough**:
- `hash` — identity (content-derived, stateless, cross-runtime comparable)
- `type` — coarse discriminator for dispatch (registries, projections, renderers)
- `payload` — arbitrary body
- `tags` — marker set (filter / index / categorize without touching `type`)

No `id`-vs-`hash` split, no `kind` flag, no `meta` object, no ceremony. More than this is premature structure.

---

## The Registry: `Namescope`

`wip/atom_prototype/src/namescope.ts` is both the **entry registry** (`Map<Hash, VirtualTypeEntry>`) and the **name overlay**. It implements the two-detached-list pattern:

```
         LEFT (consumers)      one-way ref        RIGHT (Namescope)
         ┌──────────────┐   ─────────────▶        ┌────────────────────────┐
         │ cell_A       │                          │ virtual type catalog   │
         │ cell_B       │                          │   hash → VirtualTypeEntry│
         │ cell_C       │                          │                        │
         └──────────────┘                          │ shared aliases         │
                                                   │   name → hash          │
                                                   │                        │
                                                   │ personal aliases       │
                                                   │   cellId → (name→hash) │
                                                   └────────────────────────┘
```

**Name resolution** (`NamescopeCell.resolve(name)`): personal → shared → undefined. Names never become identity; they are overlays that can be wiped per cell (`forgetCell`) without touching the entry catalog.

Relative names — first-class:
- **Personal aliases** live per-cell (`cellId` scoped), invisible to siblings
- **Shared aliases** live scope-wide
- Both layers together form "names relative to a scope", which stay distinct from the content-hash address

Entries themselves don't know about cells, about their names, or about other entries. Pure one-way arrow: cells → scope, never the reverse.

---

## Hierarchical Scopes: `LangScope`

`wip/atom_prototype/src/langextract.ts` — scopes nest via parent chain. Lookup walks up: if a name doesn't resolve in the current scope, climb to parent and retry. Mirrors LangChain's `RunnableConfig` nesting and our broader "scope boundary" model.

This lets the same wrapper participate in nested name spaces (per-document, per-session, per-agent) without the wrapper itself caring about nesting.

---

## Collections: `AtomicListBase<T>`

`wip/atom_prototype/src/atomic-list.ts` — one interface, two key-space variants, both generic over `T = unknown`. Elements may be anything — primitives, records, nested lists, mixed freely.

```ts
export interface AtomicListBase<T> {
  readonly kind: 'array' | 'nested'
  readonly size: number
  items(): T[]
  keys(): Array<number | string>
  entries(): Array<[number | string, T]>
  get(key: number | string): T | undefined
  has(key: number | string): boolean
  add(item: T): number | string
  remove(key: number | string): boolean
  clear(): void
  toJSON(): unknown
}
```

- **`ArrayAtomicList`** — keys = integer positions (`0, 1, 2, …`)
- **`NestedAtomicList`** — keys = content-hashes (`<schema>|<value>`), automatic dedup

### Abstract elements — objects and lists travel uniformly

Because `T = unknown`, the same collection instance accepts records, scalars, and nested lists simultaneously — no pre-declaration, no conversion, no shape coercion. Directly from `wip/atom_prototype/src/views/AtomicListView.vue`:

```ts
arrayList<unknown>([
  { name: 'alice', age: 30 },     // object
  { name: 'bob',   age: 25 },     // object with identical schema → dedup-able in Nested
  42,                              // primitive (number)
  'hello',                         // primitive (string)
])
```

`computeAtomicHash` derives the `schemaPart` / `valuePart` per element structurally (`deriveSchema` infers shape at one level; `localType` covers `object / array / number / string / null`), so **object-ness is free**: a record is just a valid element whose schema is `object(age,name)`. A scalar is an element whose schema is `number()`. A nested list is an element whose schema is `array()`. Wrapping, unwrapping, and passing between lists preserves structure — no custom type is declared, none is needed.

### Why this suffices for "Object by ID"

The obvious missing variant would be a third kind keyed by **human names** (a `Record<string, T>` accessor). It's absent by design:

- **Content-identified membership** (object looked up by what it *is*) → `NestedAtomicList` — key is the hash, dedup is automatic.
- **Presentation-identified access** (field `foo.bar` in a rendered card) → projection over the element's payload. Namescope's shared + personal aliases give relative-name resolution without burning names into the collection primitive.
- **Stable-ID semantics** (object `msg_1` remains `msg_1` after edit) → Namescope alias `msg_1 → hash`, or a `tags: ['id:msg_1']` marker on the wrapping entry.

All three needs are served without adding a third variant. The collection stays two-kind; naming stays overlay.

### Hash mechanics

`computeAtomicHash`: `schemaPart = <localType>(<sorted rel fields>)`, `valuePart = <fieldValueType>:<canonical JSON>`, joined as `<schemaPart>|<valuePart>`. Human-readable by design (swap to blake3/xxh3 where compactness matters). Identical content → identical hash → shared slot. Equal regardless of how an element was constructed or where it came from — the content-addressable identity from the §Purpose slogan, made concrete.

---

## Runtime Projections: `Extractor`

`wip/atom_prototype/src/extractors.ts` — named projections catalog, directly modeled on IntelliJ Database's `data/extractors/*.groovy`:

```ts
export interface Extractor {
  id: string
  label: string
  category: 'extractor' | 'aggregator' | 'schema' | 'layout'
  format: string                             // mime hint
  description?: string
  run: (rows: Row[]) => string               // pure, deterministic
}
```

Built-ins: `csv`, `json`, `md`, `sql-insert`, `python-df`, `pretty`, `ipynb`, plus aggregators (`count`, `sum`, `avg`) and identity projections (`json`, `csv-line`, `key-value`, `sql-single`, `primary-key`, `atom-uri`, `row-index`, `mime-bundle`).

Key property: **same entry, N representations**. Pick projection at read time via `runExtractor(id, rows)`. Matches IntelliJ's Copy submenu and IPython's `_repr_mimebundle_` — the atom carries truth once, projections multiply.

Extractors are registered like any other op (via `registerExtractor`) and can run wrapped (caching / logging / timing — see `AtomRegistry` wrappers). A projection is just a named function over payload; the wrapper doesn't change.

---

## Previous Shapes vs Wrapper Representation

The older runtime shapes should **not** be read as semantically collapsing into one wrapper.

`VirtualTypeEntry` is best understood as a **catalog / wrapper representation**, not as a full replacement for the original runtime meaning of every shape.

### Important disclaimer

The following mappings are representation-oriented only.

They do **not** mean:

- the runtime semantics are identical
- the lifecycle is identical
- the object role inside a module is identical

This distinction matters especially when comparing old branches, old projects, or similar names reused in different modules.

| Previous shape | Runtime meaning | Possible wrapper / catalog representation |
|----------------|-----------------|-------------------------------------------|
| `VirtualObject` | virtual runtime form; closer to a type-like object without a concrete instance payload of its own | may be represented as a `VirtualTypeEntry`, but that wrapper does not exhaust its runtime semantics |
| `VirtualList` (array) | detached grouping / ordered scope / hierarchical carrier | may be represented by `ArrayAtomicList`, optionally wrapped if cataloged |
| `VirtualList` (dedup) | detached dedup-aware grouping / alias-path and scope abstraction | may be represented by `NestedAtomicList`, optionally wrapped if cataloged |
| `RefObject` | real runtime instance resolved through reference to another object's cached/runtime-resolved state | may be represented through a wrapper or alias, but is not "still just a virtual type" |
| `AtomicRuntimeObject` | live runtime object before serialization/reference burial | may be cataloged, but remains a runtime object; after serialization it may additionally become reference-addressable |
| `ExecScope` | execution-oriented scope form; often better understood as a particular scope/list wrapping around reachable runtime objects relative to an execution endpoint | may be cataloged as a wrapper entry, but should not be reduced to a single fixed "channel" type |
| Lexical node | concrete editor/runtime node shape | may be wrapped for catalog/storage purposes |
| Jupyter cell | concrete notebook/runtime cell shape | may be wrapped for catalog/storage purposes |
| LangExtract span | extracted annotation/runtime span shape | may be atomized or wrapped depending on use |

### Correct reading

So the correct statement is:

- many shapes may be **cataloged through** `VirtualTypeEntry`
- but they do **not** semantically collapse into it

This is one of the key differences between the older universal-wrapper framing and the newer clean-room architecture direction.

---

## Migration Path

`koboldcpp-sandbox/src/data/` currently has `VirtualObject` and `VirtualList` as distinct types. Collapse incrementally.

**M0 — type alias** (zero-risk, land immediately)

```ts
// koboldcpp-sandbox/src/data/types.ts
import type { VirtualTypeEntry } from '../../../wip/atom_prototype/src/namescope'

export type VirtualObject = VirtualTypeEntry
export type VirtualList   = VirtualTypeEntry  // payload = AtomicListBase instance or its toJSON()
```

Call sites keep compiling via alias.

**M1 — Store uses Namescope** (one PR)

Replace ad-hoc `Map<string, VirtualObject>` in `Store` with a `Namescope` instance. Mutation ops that used to bump `VirtualObject.version` signal now operate on the registry + trigger version signal from there.

**M2 — Collections via AtomicListBase** (one PR)

Any `VirtualList` usage that wanted "positional list" switches to `ArrayAtomicList`. Any usage that wanted "dedup-aware bag" switches to `NestedAtomicList`. Wrapping them in a `VirtualTypeEntry` is optional — depends on whether the list itself needs a content-hash identity separate from its payload.

**M3 — Projections via Extractor catalog** (optional, per-feature)

The existing projection code in `koboldcpp-sandbox/src/runtime/` gets re-expressed as Extractor registrations where convenient. Not required for correctness; a clean path if we want uniform catalog semantics.

Each phase lands independently; M0 is pure type aliasing and can go first. Rollback is straightforward.

---

## Minimal Invariants (testable)

Most invariants are already enforced by the 109 tests in `wip/atom_prototype/src/*.test.ts`. At the repo-level migration layer, the new ones are:

1. **Wrapper uniformity**: every runtime object produced by the `koboldcpp-sandbox` side serializes to a `VirtualTypeEntry` shape (`{hash, type, payload, tags?}`).
2. **Identity = content hash**: two serializations of identical payload + type + tags produce the same `hash`.
3. **Name ≠ identity**: looking up by `hash` works without any Namescope; looking up by name requires a scope context.
4. **Collection primitives suffice**: any ordered or keyed collection in migrated code is represented by `ArrayAtomicList` or `NestedAtomicList` (or a payload reducible to one).
5. **Projections pure**: extractors don't mutate entries or the registry; calling them twice yields identical output on unchanged input.

---

## Relationship to Compute-`Atom`

The compute unit `Atom` in `wip/atom_prototype/src/atom.ts` is **different** — `{id, kind, inScope, op, outScope, payload, tags, wrappers}`. It represents an op + its IO wiring, not a data wrapper. Convention in prototype code:

- `VirtualTypeEntry` → **data** (what flows through)
- `Atom` → **operation** (what transforms)
- `Atom.inScope` / `Atom.outScope` hold refs (`AtomRef = string`) that resolve through the registry — values flowing through are `VirtualTypeEntry.payload`

If naming collision becomes painful later, rename compute-unit to `AtomOp` — the 109 tests would still pass, and the terminology separates data-atom vs op-atom cleanly.

---

## Open Questions

1. **Hash function swap**: keep `computeAtomicHash`'s human-readable format (`<schema>|<value>`) for dev, switch to blake3/xxh3 prefix for wire? Probably both — readable in dev tooling, compact hash in serialized messages.

2. **Where does payload-typed dispatch live?** Currently: via `type: string` + per-consumer switch. Could graduate to a `TypeHandler` registry if duplication becomes painful, but not necessary now — Namescope catalog + extractor registry cover current use cases.

3. **Generation vs pure content hash**: mutation under pure-hash identity produces a new `hash`. For use cases that want stable external IDs across edits (`message:msg_1` sticks), overlay via Namescope alias or `tags: ['id:msg_1']`. Good enough unless we hit frequent-mutation pressure.

4. **Leaf value storage**: inline in `payload` for now (`{value: ...}` convention). If leaves become hot enough to dominate memory, move to external key-value store addressed by hash; interface doesn't change.

---

## References

- **Canonical wrapper**: `wip/atom_prototype/src/namescope.ts:44-49` — `VirtualTypeEntry`
- **Registry + aliases**: `wip/atom_prototype/src/namescope.ts` — `Namescope`, `NamescopeCell`
- **Hierarchical scopes**: `wip/atom_prototype/src/langextract.ts` — `LangScope` parent chain
- **Collections**: `wip/atom_prototype/src/atomic-list.ts` — `AtomicListBase<T>`, `ArrayAtomicList`, `NestedAtomicList`, `computeAtomicHash`
- **Runtime projections**: `wip/atom_prototype/src/extractors.ts` — `Extractor` catalog, built-in extractors + identity projections + aggregators
- **Compute unit** (different primitive): `wip/atom_prototype/src/atom.ts` — `Atom`, `AtomRegistry`, wrappers
- **Principle source**: `C:\llm\atom-prototype-backup-2026-04-18\SESSION_SUMMARY.md` §«Architectural principles distilled» — especially §1 (MOV-wrapped refs), §5 (names opt-in over hash UIDs), §7 (same atom, N representations), §10 (hierarchical scopes)
- **Predecessors to migrate**: `koboldcpp-sandbox/src/data/types.ts` — `VirtualObject`, `VirtualList`
- **Handoff context**: `wip/HANDOFF_2026_04_18.md` §1 — "Minimal primitives = object + directed list"
