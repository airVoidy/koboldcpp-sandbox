<script setup lang="ts">
import { computed, ref } from 'vue'
import {
  listExtractors,
  runExtractor,
  listIdentityProjections,
  runIdentityProjection,
  type Row,
} from '../extractors'

/**
 * IntelliJ-style extractor catalog + right-click context menu.
 * Same data → N named projections. Pick from menu, output shown below.
 */

// Seeded demo data — simple people table.
const rows = ref<Row[]>([
  { id: 1, name: 'Alice', role: 'eng', years: 5, active: true },
  { id: 2, name: 'Bob', role: 'designer', years: 3, active: true },
  { id: 3, name: 'Carol', role: 'pm', years: 7, active: false },
  { id: 4, name: 'Dave', role: 'eng', years: 2, active: true },
])

const selected = ref<Set<number>>(new Set())

function toggleSelect(i: number) {
  const next = new Set(selected.value)
  if (next.has(i)) next.delete(i)
  else next.add(i)
  selected.value = next
}

function selectAll() {
  selected.value = new Set(rows.value.map((_, i) => i))
}
function selectNone() {
  selected.value = new Set()
}

const targetRows = computed<Row[]>(() => {
  if (selected.value.size === 0) return rows.value
  return rows.value.filter((_, i) => selected.value.has(i))
})

const extractors = listExtractors('extractor')
const aggregators = listExtractors('aggregator')
const identityProjections = listIdentityProjections()

/* --- context menu state --- */
interface MenuState {
  open: boolean
  x: number
  y: number
  /** If set, right-click targeted a single row; show row-identity menu too. */
  rowIndex: number | null
}
const menu = ref<MenuState>({ open: false, x: 0, y: 0, rowIndex: null })

function openMenu(e: MouseEvent, rowIndex?: number) {
  e.preventDefault()
  // If right-click happened on a specific row and it wasn't selected, select it
  if (rowIndex != null && !selected.value.has(rowIndex)) {
    selected.value = new Set([rowIndex])
  }
  menu.value = { open: true, x: e.clientX, y: e.clientY, rowIndex: rowIndex ?? null }
}

function closeMenu() {
  menu.value.open = false
}

/* --- extractor output --- */
const output = ref<{ id: string; label: string; format: string; text: string } | null>(null)

function runByAtom(id: string) {
  const text = runExtractor(id, targetRows.value)
  const x = [...extractors, ...aggregators].find((e) => e.id === id)!
  output.value = { id: x.id, label: x.label, format: x.format, text }
  closeMenu()
}

async function runIdentity(id: string) {
  if (menu.value.rowIndex == null) return
  const row = rows.value[menu.value.rowIndex]
  const text = runIdentityProjection(id, row, {
    rowIndex: menu.value.rowIndex,
    tableName: 'people',
  })
  const p = identityProjections.find((x) => x.id === id)!
  output.value = { id: p.id, label: `Copy row: ${p.label}`, format: p.format, text }
  // Attempt clipboard copy immediately — matches IntelliJ "Copy as" UX.
  try {
    await navigator.clipboard.writeText(text)
  } catch {
    /* clipboard unavailable */
  }
  closeMenu()
}

async function copyOutput() {
  if (!output.value) return
  try {
    await navigator.clipboard.writeText(output.value.text)
  } catch {
    /* clipboard unavailable */
  }
}

function addRow() {
  rows.value.push({
    id: rows.value.length + 1,
    name: 'New person ' + (rows.value.length + 1),
    role: 'eng',
    years: Math.floor(Math.random() * 10),
    active: true,
  })
}

const columns = computed(() => {
  const set = new Set<string>()
  for (const r of rows.value) for (const k of Object.keys(r)) set.add(k)
  return [...set]
})
</script>

<template>
  <div class="container" @click="closeMenu">
    <h1>Extractors — named projections with context menu</h1>
    <p class="subtitle">
      Same row data → many named output formats. Right-click a row (or table) →
      pick an extractor. Aggregators in the same menu compute column stats.
      Pattern from IntelliJ's <code>com.intellij.database/data/extractors/</code>.
    </p>

    <div class="controls">
      <button @click="addRow">+ row</button>
      <button @click="selectAll">select all</button>
      <button @click="selectNone">select none</button>
      <span class="hint">
        {{ selected.size }} selected — right-click the table to extract
        <span v-if="selected.size === 0">(will use all rows if none selected)</span>
      </span>
    </div>

    <table class="rows" @contextmenu="openMenu($event)">
      <thead>
        <tr>
          <th class="check">✓</th>
          <th v-for="c in columns" :key="c">{{ c }}</th>
        </tr>
      </thead>
      <tbody>
        <tr
          v-for="(r, i) in rows"
          :key="i"
          :class="{ selected: selected.has(i) }"
          @click.stop="toggleSelect(i)"
          @contextmenu.stop="openMenu($event, i)"
        >
          <td class="check">{{ selected.has(i) ? '●' : '' }}</td>
          <td v-for="c in columns" :key="c">{{ r[c] }}</td>
        </tr>
      </tbody>
    </table>

    <!-- context menu -->
    <div
      v-if="menu.open"
      class="ctx-menu"
      :style="{ left: menu.x + 'px', top: menu.y + 'px' }"
      @click.stop
    >
      <!-- Row-specific "Copy as..." section — visible only when right-clicked a row.
           Mirrors IntelliJ's Copy submenu (Absolute Path / File Name / Toolbox URL). -->
      <template v-if="menu.rowIndex != null">
        <div class="ctx-section-label">Copy row as… (clipboard)</div>
        <button
          v-for="p in identityProjections"
          :key="p.id"
          class="ctx-item"
          :title="p.description"
          @click="runIdentity(p.id)"
        >
          <span class="ctx-label">{{ p.label }}</span>
          <span class="ctx-fmt">{{ p.format }}</span>
        </button>
        <div class="ctx-divider" />
      </template>

      <div class="ctx-section-label">Extract {{ selected.size > 0 ? `${selected.size} selected` : 'all' }} as…</div>
      <button
        v-for="x in extractors"
        :key="x.id"
        class="ctx-item"
        @click="runByAtom(x.id)"
      >
        <span class="ctx-label">{{ x.label }}</span>
        <span class="ctx-fmt">{{ x.format }}</span>
      </button>
      <div class="ctx-section-label">Aggregators</div>
      <button
        v-for="a in aggregators"
        :key="a.id"
        class="ctx-item"
        @click="runByAtom(a.id)"
      >
        <span class="ctx-label">{{ a.label }}</span>
        <span class="ctx-fmt">{{ a.format }}</span>
      </button>
    </div>

    <!-- output -->
    <section v-if="output" class="output">
      <div class="output-head">
        <strong>{{ output.label }}</strong>
        <span class="output-fmt">{{ output.format }}</span>
        <button class="small" @click="copyOutput">copy</button>
        <button class="small" @click="output = null">close</button>
      </div>
      <pre>{{ output.text }}</pre>
    </section>
  </div>
</template>

<style scoped>
.controls {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 12px 0;
}
.hint {
  color: #6e6a86;
  font-size: 12px;
}

.rows {
  width: 100%;
  border-collapse: collapse;
  background: #1a1a1f;
  border: 1px solid #403d52;
  border-radius: 4px;
  overflow: hidden;
  font-size: 13px;
}
.rows th {
  background: #2a2a33;
  color: #c4a7e7;
  text-align: left;
  padding: 8px 10px;
  border-bottom: 1px solid #403d52;
  font-size: 12px;
}
.rows td {
  padding: 6px 10px;
  border-bottom: 1px solid #2a2a33;
  color: #e0def4;
}
.rows tr {
  cursor: pointer;
}
.rows tr:hover td {
  background: #2a2a33;
}
.rows tr.selected td {
  background: #403d52;
}
.check {
  width: 28px;
  text-align: center;
  color: #9ccfd8;
}

.ctx-menu {
  position: fixed;
  background: #1a1a1f;
  border: 1px solid #6e6a86;
  border-radius: 4px;
  padding: 4px;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.6);
  z-index: 10000;
  min-width: 240px;
}
.ctx-section-label {
  color: #6e6a86;
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 0.1em;
  padding: 6px 10px 2px 10px;
}
.ctx-divider {
  height: 1px;
  background: #403d52;
  margin: 4px 8px;
}
.ctx-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  width: 100%;
  background: transparent;
  border: none;
  color: #e0def4;
  padding: 6px 10px;
  border-radius: 3px;
  cursor: pointer;
  font-family: inherit;
  font-size: 13px;
  text-align: left;
}
.ctx-item:hover {
  background: #403d52;
}
.ctx-label {
  color: #e0def4;
}
.ctx-fmt {
  color: #6e6a86;
  font-size: 11px;
  font-family: ui-monospace, monospace;
}

.output {
  margin-top: 18px;
  background: #0f0f14;
  border: 1px solid #403d52;
  border-radius: 4px;
  padding: 12px;
}
.output-head {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 8px;
}
.output-head strong {
  color: #c4a7e7;
}
.output-fmt {
  color: #6e6a86;
  font-size: 11px;
  font-family: ui-monospace, monospace;
  flex: 1;
}
.output pre {
  margin: 0;
  background: #1a1a1f;
  color: #f6c177;
  padding: 10px;
  border-radius: 3px;
  overflow-x: auto;
  font-size: 12px;
  max-height: 400px;
}

button {
  background: #403d52;
  color: #e0def4;
  border: 1px solid #6e6a86;
  padding: 4px 10px;
  border-radius: 3px;
  cursor: pointer;
  font-size: 12px;
  font-family: inherit;
}
button:hover {
  background: #524f67;
}
button.small {
  font-size: 11px;
  padding: 3px 8px;
}

code {
  background: transparent;
  font-family: ui-monospace, monospace;
  color: #f6c177;
}
</style>
