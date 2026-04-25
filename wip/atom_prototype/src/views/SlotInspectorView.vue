<script setup lang="ts">
import { computed, ref, shallowRef, watch } from 'vue'
import {
  $createParagraphNode,
  $createTextNode,
  $getRoot,
  type LexicalEditor,
} from 'lexical'
import EditorHost from '../components/EditorHost.vue'
import {
  AtomicStore,
  ProjectionPipeline,
  createAtomicObject,
  createAtomicRule,
  createProjectionSlot,
  type ProjectionSlot,
} from '../cleanroom'

/**
 * ProjectionSlot ↔ Lexical bridge demo.
 *
 * Shows the pipeline working live: declared slots advance through
 * resolving → materialized | shadow | problem, with each transition
 * appended as a paragraph in a Lexical editor. The cell-as-computation-place
 * principle is made visible — the slot's vector + state are shown next to
 * its (eventually) materialized value.
 */

const editor = shallowRef<LexicalEditor | null>(null)
const tick = ref(0)

const store = new AtomicStore()
const pipeline = new ProjectionPipeline(store)

// Set up a small playground: a "double" rule resolver, an attached rule,
// and three slots with different vector kinds.
pipeline.registerRuleResolver('double', (body) => {
  const value = (body as { value: number }).value
  return value * 2
})

store.putObject(createAtomicObject('demo', null))
store.attachRule('demo', createAtomicRule('r-double-21', { kind: 'double', value: 21 }))

store.declareSlot(
  createProjectionSlot('slot:literal', 'demo', { kind: 'literal', value: 'hello world' }),
)
store.declareSlot(
  createProjectionSlot('slot:rule', 'demo', { kind: 'rule', ruleKind: 'double' }),
)
store.declareSlot(
  createProjectionSlot('slot:slotRef', 'demo', { kind: 'slotRef', slotId: 'slot:literal' }),
)
store.declareSlot(
  createProjectionSlot('slot:problem', 'demo', { kind: 'slotRef', slotId: 'absent' }),
)
store.declareSlot(
  createProjectionSlot('slot:compose', 'demo', {
    kind: 'compose',
    inputs: [
      { kind: 'slotRef', slotId: 'slot:literal' },
      { kind: 'rule', ruleKind: 'double' },
    ],
  }),
)

const slots = computed(() => {
  // eslint-disable-next-line @typescript-eslint/no-unused-expressions
  tick.value
  return [...store.slots.values()]
})

function appendToEditor(line: string) {
  const ed = editor.value
  if (!ed) return
  ed.update(() => {
    const root = $getRoot()
    const p = $createParagraphNode()
    p.append($createTextNode(line))
    root.append(p)
  })
}

function describeVector(slot: ProjectionSlot): string {
  const v = slot.vector
  if (v && typeof v === 'object' && !Array.isArray(v)) {
    const dispatch = v as { kind?: unknown }
    if (typeof dispatch.kind === 'string') return `${dispatch.kind}(${JSON.stringify(v)})`
  }
  return JSON.stringify(v)
}

function resolve(slotId: string, asShadow: boolean = false) {
  const before = store.slots.get(slotId)
  const beforeState = before?.state ?? '?'
  const result = pipeline.resolveSlot(slotId, asShadow ? { asShadow: true } : undefined)
  tick.value++

  const summary = `${slotId}: ${beforeState} → ${result.state}` +
    (result.state === 'materialized' || result.state === 'shadow'
      ? `   value=${JSON.stringify(result.value)}`
      : result.state === 'problem'
      ? `   error="${pipeline.getError(slotId) ?? 'unknown'}"`
      : '')
  appendToEditor(summary)
}

function fork(slotId: string) {
  const shadowId = `${slotId}:shadow:${tick.value + 1}`
  pipeline.forkShadow(slotId, shadowId)
  tick.value++
  appendToEditor(`forked ${slotId} → ${shadowId} (declared, ready to resolve as shadow)`)
}

watch(editor, (e) => {
  if (e) appendToEditor('— pipeline ↔ Lexical bridge ready —')
})
</script>

<template>
  <div class="slot-view">
    <h1>ProjectionSlot ↔ Lexical bridge</h1>
    <p class="hint">
      Slot lifecycle is made visible. Each <code>resolve</code> click
      transitions a slot and appends the transition as a paragraph in the
      Lexical editor below — the editor IS the computation log surface, not
      a separate inspector.
    </p>

    <table class="slots">
      <thead>
        <tr>
          <th>id</th>
          <th>state</th>
          <th>vector</th>
          <th>value / error</th>
          <th>actions</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="slot in slots" :key="slot.id" :class="`row-${slot.state}`">
          <td>{{ slot.id }}</td>
          <td><span class="badge" :class="`badge-${slot.state}`">{{ slot.state }}</span></td>
          <td><code>{{ describeVector(slot) }}</code></td>
          <td>
            <code v-if="slot.state === 'materialized' || slot.state === 'shadow'">{{ JSON.stringify(slot.value) }}</code>
            <code v-else-if="slot.state === 'problem'" class="error">{{ pipeline.getError(slot.id) ?? '—' }}</code>
            <span v-else class="muted">—</span>
          </td>
          <td>
            <button @click="resolve(slot.id)">resolve</button>
            <button v-if="slot.state === 'declared'" @click="resolve(slot.id, true)">resolve as shadow</button>
            <button @click="fork(slot.id)">fork</button>
          </td>
        </tr>
      </tbody>
    </table>

    <h2>Lexical log</h2>
    <EditorHost @ready="(e) => (editor = e)" />
  </div>
</template>

<style scoped>
.slot-view {
  padding: 1.5rem 2rem;
  max-width: 1200px;
  margin: 0 auto;
  font-family: ui-monospace, SFMono-Regular, monospace;
  color: var(--text, #e0def4);
}

h1 {
  margin: 0 0 0.5rem;
  font-size: 1.4rem;
}

h2 {
  margin: 1.5rem 0 0.5rem;
  font-size: 1rem;
  font-weight: normal;
  color: var(--muted, #908caa);
}

.hint {
  color: var(--muted, #908caa);
  line-height: 1.5;
}

code {
  background: rgba(255, 255, 255, 0.06);
  padding: 0.05rem 0.35rem;
  border-radius: 3px;
  font-size: 0.85rem;
}

code.error {
  color: #eb6f92;
}

.muted {
  color: rgba(144, 140, 170, 0.4);
}

table.slots {
  width: 100%;
  border-collapse: collapse;
  margin: 1rem 0;
  font-size: 0.85rem;
}

table.slots th,
table.slots td {
  text-align: left;
  padding: 0.5rem 0.6rem;
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
  vertical-align: top;
}

table.slots th {
  color: var(--muted, #908caa);
  font-weight: normal;
}

.badge {
  display: inline-block;
  padding: 0.1rem 0.5rem;
  border-radius: 3px;
  font-size: 0.75rem;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.badge-declared {
  background: rgba(196, 167, 231, 0.18);
  color: #c4a7e7;
}

.badge-resolving {
  background: rgba(246, 193, 119, 0.2);
  color: #f6c177;
}

.badge-materialized {
  background: rgba(156, 207, 216, 0.2);
  color: #9ccfd8;
}

.badge-shadow {
  background: rgba(196, 167, 231, 0.4);
  color: #c4a7e7;
  font-style: italic;
}

.badge-problem {
  background: rgba(235, 111, 146, 0.2);
  color: #eb6f92;
}

button {
  background: rgba(196, 167, 231, 0.14);
  border: 1px solid rgba(196, 167, 231, 0.4);
  color: var(--text, #e0def4);
  padding: 0.25rem 0.55rem;
  cursor: pointer;
  border-radius: 3px;
  font-family: inherit;
  font-size: 0.8rem;
  margin-right: 0.25rem;
}

button:hover {
  background: rgba(196, 167, 231, 0.28);
}
</style>
