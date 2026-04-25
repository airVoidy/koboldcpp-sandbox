<script setup lang="ts">
import { computed, ref } from 'vue'
import {
  AtomicStore,
  createAtomicList,
  AabbLayout,
  type Zone,
} from '../cleanroom'

/**
 * Three-zone (-1 / 0 / +1) AABB layout viewer.
 *
 * Shows a list as three buckets (past / current / future). Move items
 * between zones with arrow buttons. Default semantics are informal —
 * zones are just mutable buckets per the architecture agreement.
 */

const store = new AtomicStore()
store.putList(
  createAtomicList('demo', ['msg-1', 'msg-2', 'msg-3', 'msg-4', 'msg-5']),
)
const layout = new AabbLayout(store)
layout.createLayout('demo.zones', 'demo')

// Reactivity tick — bumped after every mutation so computeds refresh.
const tick = ref(0)

const aabb = computed(() => {
  // eslint-disable-next-line @typescript-eslint/no-unused-expressions
  tick.value
  return layout.getLayout('demo.zones')!
})

const zoneDescriptors: Array<{ key: '-1' | '0' | '+1'; label: string; value: Zone }> = [
  { key: '-1', label: '[-1] past', value: -1 },
  { key: '0', label: '[0] current', value: 0 },
  { key: '+1', label: '[+1] future', value: 1 },
]

function move(item: string, from: Zone, to: Zone) {
  layout.moveItem('demo.zones', item, from, to)
  tick.value++
}

function checkpoint(item: string) {
  layout.checkpoint('demo.zones', item)
  tick.value++
}

function archive(item: string) {
  layout.archive('demo.zones', item)
  tick.value++
}

function addNewItem() {
  const id = `msg-${aabb.value.zones['-1'].items.length + aabb.value.zones['0'].items.length + aabb.value.zones['+1'].items.length + 1}`
  layout.addToZone('demo.zones', id, 1)
  tick.value++
}

const flatPreview = computed(() => {
  // eslint-disable-next-line @typescript-eslint/no-unused-expressions
  tick.value
  return layout.flatten('demo.zones')
})
</script>

<template>
  <div class="aabb-view">
    <h1>Aabb Layout — three-zone list</h1>
    <p class="hint">
      Each list lives in three zones: past (-1), current (0), future (+1).
      The zones are not strict notation — they are mutable buckets you can
      shuffle items between. Default semantics: <code>checkpoint</code>
      promotes +1 → 0; <code>archive</code> demotes 0 → -1.
    </p>

    <div class="actions">
      <button @click="addNewItem">+ add item to [+1]</button>
    </div>

    <div class="zones">
      <div
        v-for="zone in zoneDescriptors"
        :key="zone.key"
        class="zone"
        :class="`zone-${zone.key}`"
      >
        <h2>{{ zone.label }}</h2>
        <ul v-if="aabb.zones[zone.key].items.length > 0">
          <li v-for="item in aabb.zones[zone.key].items" :key="item">
            <button
              v-if="zone.value !== -1"
              class="arrow"
              @click="move(item, zone.value, ((zone.value as number) - 1) as Zone)"
              title="move to past"
            >
              ←
            </button>
            <span class="chip">{{ item }}</span>
            <button
              v-if="zone.value !== 1"
              class="arrow"
              @click="move(item, zone.value, ((zone.value as number) + 1) as Zone)"
              title="move to future"
            >
              →
            </button>
            <button
              v-if="zone.value === 1"
              class="quick"
              @click="checkpoint(item)"
              title="checkpoint: promote to current"
            >
              ✓
            </button>
            <button
              v-if="zone.value === 0"
              class="quick"
              @click="archive(item)"
              title="archive: demote to past"
            >
              ⌫
            </button>
          </li>
        </ul>
        <p v-else class="empty">[ empty ]</p>
      </div>
    </div>

    <div class="flat">
      <h3>flatten() preview ([-1] → [0] → [+1])</h3>
      <code>{{ flatPreview.length === 0 ? '[ empty ]' : flatPreview.join(' · ') }}</code>
    </div>
  </div>
</template>

<style scoped>
.aabb-view {
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

.hint {
  margin: 0.5rem 0 1.5rem;
  color: var(--muted, #908caa);
  line-height: 1.5;
}

code {
  background: rgba(255, 255, 255, 0.06);
  padding: 0.05rem 0.35rem;
  border-radius: 3px;
}

.actions {
  margin-bottom: 1rem;
}

.actions button {
  background: rgba(196, 167, 231, 0.18);
  border: 1px solid rgba(196, 167, 231, 0.45);
  color: var(--text, #e0def4);
  padding: 0.4rem 0.8rem;
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

.zone h2 {
  margin: 0 0 0.6rem;
  font-size: 0.95rem;
  font-weight: normal;
  color: var(--muted, #908caa);
}

.zone-0 {
  border-color: rgba(196, 167, 231, 0.4);
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
}

.chip {
  flex: 1;
  background: rgba(255, 255, 255, 0.06);
  padding: 0.25rem 0.6rem;
  border-radius: 3px;
  font-size: 0.85rem;
}

.arrow,
.quick {
  background: transparent;
  border: 1px solid rgba(255, 255, 255, 0.18);
  color: var(--text, #e0def4);
  padding: 0.1rem 0.45rem;
  cursor: pointer;
  border-radius: 3px;
  font-family: inherit;
  font-size: 0.85rem;
}

.arrow:hover,
.quick:hover {
  background: rgba(196, 167, 231, 0.18);
  border-color: rgba(196, 167, 231, 0.45);
}

.empty {
  color: rgba(144, 140, 170, 0.5);
  font-style: italic;
  margin: 0.4rem 0;
}

.flat {
  margin-top: 2rem;
  padding-top: 1rem;
  border-top: 1px solid rgba(255, 255, 255, 0.08);
}

.flat h3 {
  margin: 0 0 0.5rem;
  font-size: 0.9rem;
  color: var(--muted, #908caa);
  font-weight: normal;
}
</style>
