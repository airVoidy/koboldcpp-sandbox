# Atom Prototype

Experimentation sandbox for Universal Atom pattern on top of Lexical core + Vue 3
+ Rolldown-Vite.

Not the production runtime — this is a **debug lab** for exploring concrete atom
shapes and how they project into surrounding surfaces.

## Stack

- **Vue 3** (Composition API) — reactivity model aligns with our projection/bind
  architecture. `ref`/`shallowRef` for atoms, `computed` for derived projections,
  `watch` for bind cascades.
- **Rolldown-Vite** (v7.3.1) — Rust-based bundler, faster + aligned with our
  "thin surfaces, fast bakings" philosophy.
- **Lexical core** (no `@lexical/react`) — framework-agnostic; we mount via
  `createEditor` + `setRootElement` + `registerRichText` + `registerHistory`.
  Thinner than full React wrapper.
- **synckit** — installed, not yet wired. Stub in `src/workers/resolver.worker.ts`.

## Goals

- Get Lexical running with minimum ceremony
- Define Universal Atom type + run helpers
- Demonstrate atoms dispatching Lexical commands
- Demonstrate atom-state → Vite virtual module projection
- Keep everything inspectable

## Architectural insights captured in code

### 1. Universal Atom primitive (`src/atom.ts`)

`{id, kind, inScope, op, outScope, payload, tags, wrappers}`.
One carrier, five usage modes (container / op / projection / shadow / group).
Minimum shape; everything else builds on it.

### 2. Vue reactivity ↔ our architecture (`src/App.vue`, `src/components/AtomDemo.vue`)

| Vue primitive | Our model |
|---------------|-----------|
| `shallowRef` | Atom is MOV-wrapped reference — no deep Proxy |
| `ref` / `reactive` | Accessor-overload pattern (getter/setter routing through method) |
| `computed` | Projection / derived view |
| `watch`, `watchEffect` | Bind cascade / subscription |
| Proxy boundary explicit | Accessor overload site well-defined |

### 3. Vite virtual module ≠ our Virtual Object — **one projection, not substrate** (`vite.config.ts`, `src/components/VirtualObjectDemo.vue`)

Critical framing correction:
- Our Virtual Objects are **pure assembly primitives** — runtime-operational,
  atomic, lightweight. Written fresh.
- Vite virtual modules are **build/dev-time module-space artifacts** — static
  after `load()`, frozen per HMR generation.
- Relationship is **one-way projection**: atom state → projected as Vite virtual
  module for importable access.
- Vite does not know about atoms; we inject via plugin.
- Atom lifecycle independent of Vite. Vite virtual modules are one useful
  *lens*, not the implementation substrate.

The `atom-snapshot` plugin in `vite.config.ts` demonstrates the projection
mechanism. It uses Rollup/Vite conventions:
- `resolveId(id)` returns `\0` + id to mark the module virtual
- `load(id)` returns the generated module content
- Consumer imports normally: `import snapshot from 'virtual:atom-snapshot'`

### 4. Vite environments (noted, not yet demo'd)

Vite 6+ has the Environments API — multiple isolated module graphs in one dev
server, each with its own plugin pipeline + resolution + cache.

This maps to our L0 (scope / policy boundaries) architecture:
- Each runtime container (Lexical canvas, web-container shell, markup layer,
  projection store) could be a distinct Vite environment
- Clean isolation out of the box
- Hot-swappable

Not demonstrated in this prototype yet — next iteration.

### 5. Rolldown-Vite caveat

Native Rust binding requires Node >= 20.19.0. Windows prototype runs on
20.18.1 — works but emits engine warning. Upgrade Node when convenient.

Platform binding (`@rolldown/binding-win32-x64-msvc`) had to be installed
explicitly on this machine — optional dep resolution skipped it initially.

## Run

```
cd wip/atom_prototype
npm install
npm run dev
```

Dev server at http://localhost:5177. COOP/COEP headers set for future
SharedArrayBuffer usage (synckit).

## Layout

```
src/
  main.ts                            # Vue app entry
  App.vue                            # Top-level composition, shallowRef for editor
  atom.ts                            # Universal Atom type + AtomRegistry class
  shims.d.ts                         # Vue + virtual-module ambient types
  components/
    EditorHost.vue                   # Mounts Lexical via core API (no react wrapper)
    AtomDemo.vue                     # 3 demo atoms: insert / clear / len-projection
    VirtualObjectDemo.vue            # Vite virtual module projection demo
  workers/
    resolver.worker.ts               # synckit stub (not yet wired)

vite.config.ts                       # Vue plugin + atom-snapshot virtual-module plugin
index.html                           # Dark Rosé-Pine-ish theme for readability
package.json                         # Vue 3 + rolldown-vite + lexical core
tsconfig.json                        # strict TS, vue-tsc for .vue typecheck
```

## What to try

- **Insert via Atom** — same Atom shape, `op.type = 'lambda'`, runs through registry,
  logs input/output
- **Clear via Atom** — same shape, different lambda — shows op polymorphism
- **Project text length** — read-only projection atom, doesn't mutate editor
- **Virtual module section (expandable)** — inspect the Vite-generated snapshot,
  see how an atom state *projects* into module space

## Next iterations

1. **synckit wiring** — projection delivery + worker bridge demo
2. **Vite environments demo** — separate env per container type, show isolation
3. **Shadow markup layer** — langextract-repurposed attribute overlays on text
4. **Atom composition** — chain of atoms, output of one feeds input of next
5. **Wrappers** — decorate atoms (logging, caching, access-control) without changing identity
6. **lexical-devtools integration** — play slider + command history inspector
7. **mockforge persistence** — dump atom state via HTTP mock, restore on reload
