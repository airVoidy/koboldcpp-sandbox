<script setup lang="ts">
import { computed, ref } from 'vue'
import {
  AabbLayout,
  AtomicStore,
  AtomToPlaceholderGateway,
  Payload,
  ProjectionPipeline,
  createAtomicList,
  createAtomicObject,
  createProjectionSlot,
  type Zone,
} from '../cleanroom'

/**
 * Composition demo: Gateway + Pipeline + AABB working together.
 *
 * 1. User types a message and clicks `drop`.
 * 2. Gateway routes the payload by content kind:
 *      - starts with "!"  → urgent  → zone +1 (future / needs attention)
 *      - parses as number → metric  → zone  0 (current data)
 *      - everything else  → note    → zone -1 (history)
 * 3. A new ProjectionSlot is declared with a literal vector and resolved.
 * 4. On materialize (via pipeline.onResolve), the slot id is added to the
 *    AABB zone that the gateway picked.
 *
 * The three primitives never reference each other directly — coupling
 * happens only in user code (this view), via their public APIs.
 */

const store = new AtomicStore()
const pipeline = new ProjectionPipeline(store)
const gateway = new AtomToPlaceholderGateway()
const layout = new AabbLayout(store)

store.putList(createAtomicList('inbox', []))
layout.createLayout('inbox.zones', 'inbox')

// Gateway dispatchers — match on payload content
gateway.registerDispatcher({
  id: 'urgent',
  matchKind: 'single',
  matchPayload: (p) =>
    p.kind === 'single' && typeof p.value === 'string' && p.value.startsWith('!'),
  target: 'zone:+1',
})
gateway.registerDispatcher({
  id: 'metric',
  matchKind: 'single',
  matchPayload: (p) => p.kind === 'single' && typeof p.value === 'number',
  target: 'zone:0',
})
gateway.registerDispatcher({
  id: 'note',
  matchKind: 'single',
  target: 'zone:-1',
})

const TARGET_TO_ZONE: Record<string, Zone> = {
  'zone:-1': -1,
  'zone:0': 0,
  'zone:+1': 1,
}

const tick = ref(0)
const log = ref<Array<{ id: string; gatewayTarget: string; dispatcherId: string }>>([])
const slotZone = new Map<string, Zone>()

// On every materialized slot, route into the AABB zone the gateway picked.
pipeline.onResolve(({ slot }) => {
  if (slot.state !== 'materialized') return
  const zone = slotZone.get(slot.id)
  if (zone === undefined) return
  layout.addToZone('inbox.zones', slot.id, zone)
  tick.value++
})

let counter = 0
const inputText = ref('')

function drop() {
  const text = inputText.value.trim()
  if (!text) return

  // Coerce numeric strings to numbers; everything else stays as string
  const valueIsNumber = /^-?\d+(\.\d+)?$/.test(text)
  const value = valueIsNumber ? parseFloat(text) : text

  const result = gateway.drop(Payload.single(value))
  if (!result) {
    log.value = [...log.value, { id: '(no match)', gatewayTarget: '—', dispatcherId: '—' }]
    return
  }

  counter++
  const slotId = `msg:${counter}`
  slotZone.set(slotId, TARGET_TO_ZONE[result.target])

  // Each message becomes its own atomic object + slot for clean isolation.
  store.putObject(createAtomicObject(slotId, null))
  store.declareSlot(
    createProjectionSlot(slotId, slotId, { kind: 'literal', value }),
  )

  pipeline.resolveSlot(slotId)
  log.value = [
    ...log.value,
    { id: slotId, gatewayTarget: result.target, dispatcherId: result.dispatcherId },
  ]
  inputText.value = ''
}

const aabb = computed(() => {
  // eslint-disable-next-line @typescript-eslint/no-unused-expressions
  tick.value
  return layout.getLayout('inbox.zones')!
})

function valueOf(slotId: string): string {
  const slot = store.slots.get(slotId)
  if (!slot || slot.state !== 'materialized') return '?'
  return JSON.stringify(slot.value)
}

const zoneDescriptors: Array<{ key: '-1' | '0' | '+1'; label: string; hint: string }> = [
  { key: '-1', label: '[-1] notes', hint: 'plain text → history' },
  { key: '0', label: '[0] metrics', hint: 'numbers → current data' },
  { key: '+1', label: '[+1] urgent', hint: 'starts with "!" → future / attention' },
]
</script>

<template>
  <div class="composition-view">
    <h1>Composition demo — Gateway + Pipeline + AABB</h1>
    <p class="hint">
      Type a message and drop it. Three independent primitives compose
      via the pipeline's <code>onResolve</code> hook, no direct coupling.
      Try: <code>hello</code>, <code>42</code>, <code>!alert</code>.
    </p>

    <div class="input">
      <input
        v-model="inputText"
        type="text"
        placeholder='message…'
        @keyup.enter="drop"
      />
      <button @click="drop">drop</button>
    </div>

    <div class="zones">
      <div v-for="zone in zoneDescriptors" :key="zone.key" class="zone">
        <h2>{{ zone.label }}</h2>
        <p class="zone-hint">{{ zone.hint }}</p>
        <ul v-if="aabb.zones[zone.key].items.length > 0">
          <li v-for="slotId in aabb.zones[zone.key].items" :key="slotId">
            <span class="slot-id">{{ slotId }}</span>
            <span class="arrow-sep">→</span>
            <code>{{ valueOf(slotId) }}</code>
          </li>
        </ul>
        <p v-else class="empty">[ empty ]</p>
      </div>
    </div>

    <h2 class="log-h">Routing log</h2>
    <table v-if="log.length > 0" class="log">
      <thead>
        <tr>
          <th>slot id</th>
          <th>dispatcher</th>
          <th>gateway target</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="(entry, i) in log" :key="i">
          <td>{{ entry.id }}</td>
          <td>{{ entry.dispatcherId }}</td>
          <td><code>{{ entry.gatewayTarget }}</code></td>
        </tr>
      </tbody>
    </table>
    <p v-else class="empty">[ no drops yet ]</p>
  </div>
</template>

<style scoped>
.composition-view {
  padding: 1.5rem 2rem;
  max-width: 1100px;
  margin: 0 auto;
  font-family: ui-monospace, SFMono-Regular, monospace;
  color: var(--text, #e0def4);
}

h1 {
  margin: 0 0 0.5rem;
  font-size: 1.4rem;
}

h2 {
  font-size: 0.95rem;
  font-weight: normal;
  color: var(--muted, #908caa);
  margin: 0 0 0.4rem;
}

h2.log-h {
  margin-top: 2rem;
}

.hint {
  color: var(--muted, #908caa);
  line-height: 1.5;
  margin-bottom: 1.5rem;
}

code {
  background: rgba(255, 255, 255, 0.06);
  padding: 0.05rem 0.35rem;
  border-radius: 3px;
  font-size: 0.85rem;
}

.input {
  display: flex;
  gap: 0.5rem;
  margin-bottom: 1.5rem;
}

.input input {
  flex: 1;
  padding: 0.5rem 0.75rem;
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid rgba(255, 255, 255, 0.15);
  border-radius: 4px;
  color: var(--text, #e0def4);
  font-family: inherit;
  font-size: 0.95rem;
}

.input input:focus {
  outline: none;
  border-color: rgba(196, 167, 231, 0.5);
}

.input button {
  background: rgba(196, 167, 231, 0.18);
  border: 1px solid rgba(196, 167, 231, 0.45);
  color: var(--text, #e0def4);
  padding: 0.4rem 1.2rem;
  border-radius: 4px;
  cursor: pointer;
  font-family: inherit;
}

.zones {
  display: grid;
  grid-template-columns: 1fr 1fr 1fr;
  gap: 1rem;
}

.zone {
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 6px;
  padding: 0.8rem 1rem;
  background: rgba(255, 255, 255, 0.02);
  min-height: 200px;
}

.zone-hint {
  color: rgba(144, 140, 170, 0.6);
  font-size: 0.78rem;
  margin: 0 0 0.6rem;
}

.zone ul {
  list-style: none;
  padding: 0;
  margin: 0;
}

.zone li {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  padding: 0.3rem 0;
  font-size: 0.85rem;
}

.slot-id {
  color: var(--muted, #908caa);
  font-size: 0.78rem;
}

.arrow-sep {
  color: rgba(144, 140, 170, 0.4);
}

.empty {
  color: rgba(144, 140, 170, 0.5);
  font-style: italic;
  margin: 0.4rem 0;
}

.log {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.85rem;
}

.log th,
.log td {
  text-align: left;
  padding: 0.4rem 0.6rem;
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
}

.log th {
  color: var(--muted, #908caa);
  font-weight: normal;
}
</style>
