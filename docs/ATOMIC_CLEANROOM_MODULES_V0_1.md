# Atomic Clean-Room Modules v0.1

Four independent modules that layer on top of the bootstrap
([atomic_cleanroom_bootstrap.ts](../wip/atomic_cleanroom_bootstrap.ts) /
[ATOMIC_CLEANROOM_BOOTSTRAP_V0_1.md](ATOMIC_CLEANROOM_BOOTSTRAP_V0_1.md))
without modifying it. Each grounds one of the architectural primitives from
the April 22, 2026 session in working TypeScript with vitest coverage.

Code lives at `wip/atom_prototype/src/cleanroom/`:

| Module       | File           | Purpose                                                         |
| ------------ | -------------- | --------------------------------------------------------------- |
| `pipeline`   | `pipeline.ts`  | ProjectionSlot lifecycle: declared → resolving → materialized…  |
| `aabb`       | `aabb.ts`      | Three-zone list layout (-1 / 0 / +1)                            |
| `portals`    | `portals.ts`   | GloryHole (point-to-one) + StreamGate (point-to-many)           |
| `contracts`  | `contracts.ts` | FutureContract + KeyframeUnion + CheckpointSync                 |

All four are independent — each can be used alone, none requires the others.
The bootstrap's `AtomicStore` is the only shared substrate.

## 1. ProjectionPipeline

Walks `ProjectionSlot.vector` and transitions slots through their lifecycle.
Vectors dispatch by `kind`:

- `{ kind: 'literal', value }` → returns `value` as-is
- `{ kind: 'slotRef', slotId }` → resolves another slot recursively
- `{ kind: 'rule', ruleKind }` → applies a registered resolver against an
  attached rule whose body kind matches `ruleKind`
- `{ kind: 'compose', inputs: [...] }` → resolves each input vector and
  returns array

Anything else is treated as a literal value. Cycles are detected via the
`resolving` state and produce `problem` slots with a captured error message.

```ts
import { AtomicStore, createAtomicObject, createAtomicRule, createProjectionSlot, ProjectionPipeline } from '@/cleanroom'

const store = new AtomicStore()
const pipeline = new ProjectionPipeline(store)

pipeline.registerRuleResolver('double', (body) => {
  return (body as { value: number }).value * 2
})

store.putObject(createAtomicObject('house', null))
store.attachRule('house', createAtomicRule('r', { kind: 'double', value: 21 }))
store.declareSlot(createProjectionSlot('s', 'house', { kind: 'rule', ruleKind: 'double' }))

pipeline.resolveSlot('s')
// store.slots.get('s') → { state: 'materialized', value: 42, ... }
```

`forkShadow(sourceId, shadowId, opts?)` creates a sibling slot inheriting
`vector` and `ruleRefs`, ready for independent resolution. Resolve with
`{ asShadow: true }` to mark the result as a shadow alternative.

See: [ATOMIC_PROJECTION_SLOT_SPEC_V0_1.md](ATOMIC_PROJECTION_SLOT_SPEC_V0_1.md).

## 2. AabbLayout

Three buckets (-1 / 0 / +1) per list, with optional bounding boxes for
visual placement. The zones are not strict notation — they are mutable
buckets that match the architectural agreement from
[ATOMIC_AABB_LIST_LAYOUT_V0_1.md](ATOMIC_AABB_LIST_LAYOUT_V0_1.md).

Convenience helpers: `checkpoint()` (promote +1 → 0) and `archive()`
(demote 0 → -1). Both no-op when the item is not in the source zone.

```ts
import { AabbLayout, AtomicStore, createAtomicList } from '@/cleanroom'

const store = new AtomicStore()
store.putList(createAtomicList('msgs', ['m1', 'm2', 'm3']))

const layout = new AabbLayout(store)
layout.createLayout('msgs.zones', 'msgs')

// Move m3 into +1 (optimistic future), then promote it on checkpoint.
layout.moveItem('msgs.zones', 'm3', 0, 1)
layout.checkpoint('msgs.zones', 'm3')

layout.flatten('msgs.zones') // ['m1', 'm2', 'm3']
```

## 3. Portals (GloryHole + StreamGate)

Two peer primitives in the same family, differing in cardinality:

- **GloryHole**: declare dispatchers in advance; a dropped payload is routed
  to the first dispatcher whose matcher returns true. Cardinality is
  point-to-one. Producer doesn't know which destination catches.

- **StreamGate**: emit once, deliver to all current subscribers.
  Cardinality is point-to-many. Subscriber errors are isolated (counted
  but not propagated).

`PortalRegistry(store)` lazily creates and caches both kinds by id.

```ts
import { GloryHole, StreamGate, PortalRegistry, AtomicStore } from '@/cleanroom'

const reg = new PortalRegistry(new AtomicStore())

const ingest = reg.gloryHole('inbox')
ingest.registerDispatcher('numbers', (p) => typeof p === 'number', 'slot:numbers')
ingest.registerDispatcher('strings', (p) => typeof p === 'string', 'slot:strings')

ingest.drop(42)   // → { target: 'slot:numbers', dispatcherId: 'numbers' }
ingest.drop('hi') // → { target: 'slot:strings', dispatcherId: 'strings' }

const events = reg.streamGate('events')
events.subscribe('viewer-a', (p) => console.log('a saw', p))
events.subscribe('viewer-b', (p) => console.log('b saw', p))
events.emit({ kind: 'tick' })
```

## 4. Contracts (FutureContract + CheckpointSync)

`ContractRegistry`: declarative coordination over async work.

- `declare(id, scheduledAt?)` — open a future-contract
- `prepare(id, peerId, snapshot)` — peer adds its snapshot
- `settle(id)` — produce a `KeyframeUnion`: union of all preparations,
  no principled merge (branching-as-default semantics)
- `cancel(id)` — close before settling

Contracts are idempotent on settle (returns existing keyframe).

`CheckpointSync`: append-only exec-log with predicate-driven watchers.
Watchers fire synchronously when their predicate matches a new entry.
Sync-condition is just a predicate over the log — not a separate sync
protocol machine.

```ts
import { ContractRegistry, CheckpointSync, AtomicStore } from '@/cleanroom'

const store = new AtomicStore()

// Coordinate via future-contract
const contracts = new ContractRegistry(store)
contracts.declare('milestone-1')
contracts.prepare('milestone-1', 'peerA', store.snapshot('targetA'))
contracts.prepare('milestone-1', 'peerB', store.snapshot('targetB'))
const keyframe = contracts.settle('milestone-1')
// keyframe.peerIds = ['peerA', 'peerB']
// keyframe.snapshots.peerA / .peerB are independent snapshots, not merged

// Hash-of-pattern checkpoint sync
const sync = new CheckpointSync()
sync.watch(
  'on-checkpoint',
  (e) => (e as { kind?: string }).kind === 'checkpoint',
  (entry, seq) => contracts.settle((entry as { id: string }).id),
)
sync.append({ kind: 'op', payload: 1 })
sync.append({ kind: 'checkpoint', id: 'milestone-1' })
```

## How they compose

The four modules layer around `AtomicStore`. Composition examples:

- `Pipeline` + `Portals`: GloryHole dispatchers carry payloads to specific
  slots; the slots' vectors then resolve those payloads via Pipeline.
- `Pipeline` + `Aabb`: items in a zone reference slots; the zone-promotion
  step (`checkpoint`) can be wired to call `pipeline.resolveSlot()`.
- `Contracts` + `Pipeline`: peers prepare snapshots after resolving slots
  locally; settle gives a union of all peer-resolved snapshots without
  forcing convergence.
- `CheckpointSync` + `Contracts`: predicate over the log triggers
  contract settlement automatically (e.g., when a `checkpoint` entry of
  the right shape appears).

None of these compositions require modifications to the modules — they
all happen in user code over the public APIs.

## Test coverage

Vitest run on `wip/atom_prototype` (165 tests total, 56 of which are
cleanroom):

| File                  | Tests |
| --------------------- | ----- |
| `pipeline.test.ts`    | 12    |
| `aabb.test.ts`        | 12    |
| `portals.test.ts`     | 14    |
| `contracts.test.ts`   | 18    |

Run with `pnpm test` or `npm test` from `wip/atom_prototype/`.

## Next steps

Things the cleanroom does not yet cover (deferred, pickable independently):

- **OPFS ↔ exec-checkpoint sync wire-up** — bind `CheckpointSync` to a
  real synckit OPFS storage, snapshot-on-match.
- **Atom-to-placeholder gateway** — generalize `GloryHole` to support
  ordered command groups, time-series, and other payload-shape variants.
- **Visual viewer** — Vue component(s) that render an `AabbLayout` with
  draggable zone movement, calling the existing helpers.
- **Lexical bridge** — wire `ProjectionSlot.materialized` into a Lexical
  display so live UI shows computation route, not only payload.

See [ATOMIC_CLEANROOM_ARCHITECTURE_SESSION_2026_04_22.md](ATOMIC_CLEANROOM_ARCHITECTURE_SESSION_2026_04_22.md)
for the full architectural context that produced these modules.
