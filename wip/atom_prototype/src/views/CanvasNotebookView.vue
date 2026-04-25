<script setup lang="ts">
import { reactive, ref, shallowRef } from 'vue'
import {
  loadCanvasCells,
  newCell,
  saveCanvasCells,
  seedCells,
  type CanvasCell,
  type JCellType,
  type JupyterNotebook,
} from '../canvas-notebook'

const cells = reactive<CanvasCell[]>(seedCells())
let zCounter = cells.reduce((m, c) => Math.max(m, c.z), 0) + 1

/* --- drag / resize --- */
const drag = reactive<{
  id: string | null
  mode: 'move' | 'resize'
  startX: number
  startY: number
  origX: number
  origY: number
  origW: number
  origH: number
}>({
  id: null,
  mode: 'move',
  startX: 0,
  startY: 0,
  origX: 0,
  origY: 0,
  origW: 0,
  origH: 0,
})

function focus(c: CanvasCell) {
  c.z = ++zCounter
}

function onHeaderDown(e: PointerEvent, c: CanvasCell) {
  focus(c)
  drag.id = c.id
  drag.mode = 'move'
  drag.startX = e.clientX
  drag.startY = e.clientY
  drag.origX = c.pos.x
  drag.origY = c.pos.y
  drag.origW = c.size.w
  drag.origH = c.size.h
  ;(e.currentTarget as HTMLElement).setPointerCapture(e.pointerId)
}

function onResizeDown(e: PointerEvent, c: CanvasCell) {
  focus(c)
  drag.id = c.id
  drag.mode = 'resize'
  drag.startX = e.clientX
  drag.startY = e.clientY
  drag.origX = c.pos.x
  drag.origY = c.pos.y
  drag.origW = c.size.w
  drag.origH = c.size.h
  ;(e.currentTarget as HTMLElement).setPointerCapture(e.pointerId)
  e.stopPropagation()
}

function onMove(e: PointerEvent) {
  if (!drag.id) return
  const c = cells.find((x) => x.id === drag.id)
  if (!c) return
  const dx = e.clientX - drag.startX
  const dy = e.clientY - drag.startY
  if (drag.mode === 'move') {
    c.pos.x = Math.max(0, drag.origX + dx)
    c.pos.y = Math.max(0, drag.origY + dy)
  } else {
    c.size.w = Math.max(160, drag.origW + dx)
    c.size.h = Math.max(80, drag.origH + dy)
  }
}

function onUp() {
  drag.id = null
}

/* --- cell ops --- */
function addCell(type: JCellType) {
  const x = 80 + Math.random() * 300
  const y = 80 + Math.random() * 200
  cells.push(newCell(type, x, y, ++zCounter))
}

function removeCell(id: string) {
  const i = cells.findIndex((c) => c.id === id)
  if (i >= 0) cells.splice(i, 1)
}

function activeFaceOf(c: CanvasCell): string {
  return c.activeFace ?? 'source'
}

function currentContent(c: CanvasCell): string {
  const face = activeFaceOf(c)
  if (face === 'source') return c.source
  return c.faces?.[face]?.content ?? ''
}

function updateCurrent(c: CanvasCell, value: string) {
  const face = activeFaceOf(c)
  if (face === 'source') {
    c.source = value
    return
  }
  if (!c.faces) c.faces = {}
  if (!c.faces[face]) c.faces[face] = { content: '' }
  c.faces[face].content = value
}

function switchFace(c: CanvasCell, name: string) {
  c.activeFace = name
}

function addFace(c: CanvasCell) {
  const name = prompt('New face name (e.g. notes, annotations, sql-compiled):')
  if (!name) return
  if (name === 'source') {
    alert('"source" is reserved for the primary side')
    return
  }
  if (!c.faces) c.faces = {}
  if (c.faces[name]) {
    alert(`face "${name}" already exists`)
    switchFace(c, name)
    return
  }
  c.faces[name] = { content: '' }
  switchFace(c, name)
}

function removeFace(c: CanvasCell, name: string) {
  if (name === 'source') return
  if (!c.faces) return
  delete c.faces[name]
  if (activeFaceOf(c) === name) c.activeFace = 'source'
}

function facesOf(c: CanvasCell): string[] {
  return ['source', ...Object.keys(c.faces ?? {})]
}

function changeType(c: CanvasCell, value: JCellType) {
  c.cell_type = value
  if (value === 'code') {
    if (c.outputs == null) c.outputs = []
    if (c.execution_count == null) c.execution_count = null
  } else {
    c.outputs = undefined
    c.execution_count = undefined
  }
}

/* --- import / export .ipynb --- */
const exportedJson = shallowRef<string>('')
const importJson = ref<string>('')
const importError = ref<string>('')

function exportNotebook() {
  const nb = saveCanvasCells(cells)
  exportedJson.value = JSON.stringify(nb, null, 2)
}

function importNotebook() {
  importError.value = ''
  try {
    const parsed = JSON.parse(importJson.value) as JupyterNotebook
    if (!parsed || typeof parsed !== 'object' || !Array.isArray(parsed.cells)) {
      throw new Error('not a notebook (missing cells array)')
    }
    const loaded = loadCanvasCells(parsed)
    cells.splice(0, cells.length, ...loaded)
    zCounter = cells.reduce((m, c) => Math.max(m, c.z), 0) + 1
    importJson.value = ''
  } catch (e) {
    importError.value = (e as Error).message
  }
}

async function copyExported() {
  if (!exportedJson.value) exportNotebook()
  try {
    await navigator.clipboard.writeText(exportedJson.value)
  } catch {
    /* ignore */
  }
}
</script>

<template>
  <div class="wrap">
    <header class="top">
      <h1>Canvas Notebook</h1>
      <p class="subtitle">
        Jupyter-compatible .ipynb, cells positioned freely on a 2D canvas. Position +
        size stored as text in <code>cell.metadata.atom.{pos,size}</code>. Standard Jupyter
        readers ignore the extra metadata and render linearly — file stays valid either way.
      </p>

      <div class="controls">
        <button @click="addCell('markdown')">+ markdown</button>
        <button @click="addCell('code')">+ code</button>
        <button @click="addCell('raw')">+ raw</button>
        <span class="divider" />
        <button @click="exportNotebook">export → .ipynb</button>
        <button @click="copyExported">copy json</button>
      </div>
    </header>

    <div class="canvas" @pointermove="onMove" @pointerup="onUp">
      <div
        v-for="c in cells"
        :key="c.id"
        class="cell"
        :class="'cell-' + c.cell_type"
        :style="{
          left: c.pos.x + 'px',
          top: c.pos.y + 'px',
          width: c.size.w + 'px',
          height: c.size.h + 'px',
          zIndex: c.z,
        }"
        @pointerdown="focus(c)"
      >
        <div class="cell-head" @pointerdown="onHeaderDown($event, c)">
          <select :value="c.cell_type" @change="changeType(c, ($event.target as HTMLSelectElement).value as JCellType)" @click.stop>
            <option value="markdown">markdown</option>
            <option value="code">code</option>
            <option value="raw">raw</option>
          </select>
          <span class="cell-id">{{ c.id }}</span>
          <span class="cell-pos">@ {{ Math.round(c.pos.x) }},{{ Math.round(c.pos.y) }}</span>
          <button class="close" @pointerdown.stop @click.stop="removeCell(c.id)">×</button>
        </div>
        <div class="faces-bar" @pointerdown.stop>
          <button
            v-for="name in facesOf(c)"
            :key="name"
            class="face-tab"
            :class="{ active: activeFaceOf(c) === name }"
            @click="switchFace(c, name)"
            :title="name === 'source' ? 'canonical Jupyter source (front)' : 'shadow face'"
          >
            {{ name }}
            <span
              v-if="name !== 'source'"
              class="face-remove"
              @click.stop="removeFace(c, name)"
            >×</span>
          </button>
          <button class="face-add" @click="addFace(c)" title="add a new named projection / side">+</button>
        </div>
        <textarea
          class="cell-source"
          :value="currentContent(c)"
          @input="updateCurrent(c, ($event.target as HTMLTextAreaElement).value)"
          spellcheck="false"
        />
        <div class="resize-handle" @pointerdown="onResizeDown($event, c)"></div>
      </div>
    </div>

    <section class="io">
      <details>
        <summary>Import .ipynb (paste JSON)</summary>
        <textarea v-model="importJson" placeholder='paste Jupyter notebook JSON here' class="io-textarea" rows="8" />
        <div class="io-row">
          <button @click="importNotebook">load into canvas</button>
          <span v-if="importError" class="error">{{ importError }}</span>
        </div>
      </details>

      <details v-if="exportedJson">
        <summary>Exported .ipynb JSON ({{ exportedJson.length }} chars)</summary>
        <pre class="io-pre">{{ exportedJson }}</pre>
      </details>
    </section>
  </div>
</template>

<style scoped>
.wrap {
  display: flex;
  flex-direction: column;
  height: calc(100vh - 60px);
}

header.top {
  padding: 14px 20px;
  background: #0f0f14;
  border-bottom: 1px solid #403d52;
}
h1 {
  margin: 0 0 4px 0;
  color: #9ccfd8;
}
.subtitle {
  color: #6e6a86;
  font-size: 13px;
  margin: 0 0 10px 0;
  line-height: 1.5;
}
.controls {
  display: flex;
  gap: 6px;
  align-items: center;
}
.divider {
  border-left: 1px solid #403d52;
  height: 20px;
  margin: 0 4px;
}

.canvas {
  flex: 1;
  position: relative;
  overflow: auto;
  background:
    radial-gradient(circle, #2a2a33 1px, transparent 1px) 0 0 / 20px 20px,
    #0f0f14;
  user-select: none;
}

.cell {
  position: absolute;
  background: #1a1a1f;
  border: 1px solid #403d52;
  border-radius: 6px;
  box-shadow: 0 4px 14px rgba(0, 0, 0, 0.4);
  display: flex;
  flex-direction: column;
}
.cell-markdown {
  border-left: 3px solid #9ccfd8;
}
.cell-code {
  border-left: 3px solid #c4a7e7;
}
.cell-raw {
  border-left: 3px solid #6e6a86;
}
.cell-head {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 5px 8px;
  background: #2a2a33;
  border-bottom: 1px solid #403d52;
  cursor: grab;
  font-size: 11px;
}
.cell-head:active {
  cursor: grabbing;
}
.cell-id {
  color: #6e6a86;
  font-family: ui-monospace, monospace;
  font-size: 10px;
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.cell-pos {
  color: #6e6a86;
  font-family: ui-monospace, monospace;
  font-size: 10px;
}
.close {
  background: transparent;
  border: none;
  color: #6e6a86;
  font-size: 16px;
  padding: 0 4px;
  cursor: pointer;
}
.close:hover {
  color: #eb6f92;
}
.faces-bar {
  display: flex;
  align-items: center;
  gap: 2px;
  padding: 4px 6px;
  background: #0f0f14;
  border-bottom: 1px solid #403d52;
  overflow-x: auto;
}
.face-tab {
  background: transparent;
  color: #6e6a86;
  border: 1px solid transparent;
  padding: 3px 8px;
  border-radius: 3px;
  cursor: pointer;
  font-size: 10px;
  font-family: ui-monospace, monospace;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  white-space: nowrap;
}
.face-tab:hover {
  background: #2a2a33;
  color: #e0def4;
}
.face-tab.active {
  background: #403d52;
  color: #c4a7e7;
  border-color: #6e6a86;
}
.face-remove {
  color: #6e6a86;
  font-size: 11px;
  line-height: 1;
}
.face-remove:hover {
  color: #eb6f92;
}
.face-add {
  background: transparent;
  color: #6e6a86;
  border: 1px dashed #403d52;
  padding: 3px 8px;
  border-radius: 3px;
  cursor: pointer;
  font-size: 10px;
}
.face-add:hover {
  color: #9ccfd8;
  border-color: #9ccfd8;
}

.cell-source {
  flex: 1;
  background: transparent;
  border: none;
  outline: none;
  padding: 8px 10px;
  color: #e0def4;
  font-family: ui-monospace, monospace;
  font-size: 12px;
  resize: none;
}
.cell-code .cell-source {
  color: #8ec07c;
}
.cell-raw .cell-source {
  color: #f6c177;
}
.resize-handle {
  position: absolute;
  right: 0;
  bottom: 0;
  width: 14px;
  height: 14px;
  cursor: nwse-resize;
  background: linear-gradient(135deg, transparent 50%, #6e6a86 50%);
  border-bottom-right-radius: 6px;
}

.io {
  padding: 10px 20px;
  background: #0f0f14;
  border-top: 1px solid #403d52;
  max-height: 40vh;
  overflow: auto;
}
.io details summary {
  color: #c4a7e7;
  cursor: pointer;
  font-size: 13px;
  padding: 4px 0;
}
.io-textarea {
  width: 100%;
  background: #1a1a1f;
  color: #e0def4;
  border: 1px solid #403d52;
  border-radius: 4px;
  padding: 6px 8px;
  font-family: ui-monospace, monospace;
  font-size: 11px;
  resize: vertical;
  box-sizing: border-box;
  margin-top: 4px;
}
.io-row {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 6px;
}
.error {
  color: #eb6f92;
  font-size: 12px;
}
.io-pre {
  background: #1a1a1f;
  color: #f6c177;
  padding: 8px;
  border-radius: 3px;
  font-size: 11px;
  max-height: 400px;
  overflow: auto;
}

select {
  background: #403d52;
  color: #e0def4;
  border: 1px solid #6e6a86;
  padding: 2px 4px;
  border-radius: 3px;
  font-size: 11px;
  font-family: inherit;
}
button {
  background: #403d52;
  color: #e0def4;
  border: 1px solid #6e6a86;
  padding: 5px 10px;
  border-radius: 3px;
  cursor: pointer;
  font-size: 12px;
  font-family: inherit;
}
button:hover {
  background: #524f67;
}
code {
  background: #0f0f14;
  padding: 1px 4px;
  border-radius: 2px;
  color: #f6c177;
  font-size: 12px;
}
</style>
