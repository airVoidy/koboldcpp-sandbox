<script setup lang="ts">
import { ref, reactive } from 'vue'
import { moduleEntries } from '../router'

/**
 * Floating-window workbench — all modules rendered simultaneously as iframes
 * on a single page, draggable + resizable, z-index stacked on focus.
 *
 * Each window hosts a URL served by our dev server (port 5177):
 *   - internal modules: /atom-demo, /compile, etc. — Vue Router pages
 *   - external modules: /proxy/<name>/ — server.proxy forwards
 *
 * Iframe isolation lets heterogeneous stacks (Vue, React, vanilla, Rust-WASM)
 * coexist without polluting each other's globals.
 *
 * Drag/resize is hand-rolled with pointer events; no extra deps. If this
 * grows beyond a prototype, swap in dockview-vue or golden-layout.
 */

interface Win {
  id: string
  title: string
  src: string
  x: number
  y: number
  w: number
  h: number
  z: number
}

let zCounter = 1
const windows = reactive<Win[]>([])

// Seed default windows for every registered module (internal or external),
// EXCEPT the workbench itself — preventing recursive iframe embedding.
let offset = 0
for (const entry of moduleEntries) {
  if (entry.name === 'workbench') continue
  const src = entry.external ?? entry.path ?? '/'
  windows.push({
    id: entry.name,
    title: entry.title,
    src,
    x: 20 + offset,
    y: 20 + offset,
    w: 720,
    h: 480,
    z: ++zCounter,
  })
  offset += 24
}

function bringToFront(w: Win) {
  w.z = ++zCounter
}

const dragState = ref<null | {
  id: string
  mode: 'move' | 'resize'
  startX: number
  startY: number
  origX: number
  origY: number
  origW: number
  origH: number
}>(null)

function onHeaderPointerDown(e: PointerEvent, w: Win) {
  bringToFront(w)
  dragState.value = {
    id: w.id,
    mode: 'move',
    startX: e.clientX,
    startY: e.clientY,
    origX: w.x,
    origY: w.y,
    origW: w.w,
    origH: w.h,
  }
  ;(e.currentTarget as HTMLElement).setPointerCapture(e.pointerId)
}

function onResizePointerDown(e: PointerEvent, w: Win) {
  bringToFront(w)
  dragState.value = {
    id: w.id,
    mode: 'resize',
    startX: e.clientX,
    startY: e.clientY,
    origX: w.x,
    origY: w.y,
    origW: w.w,
    origH: w.h,
  }
  ;(e.currentTarget as HTMLElement).setPointerCapture(e.pointerId)
  e.stopPropagation()
}

function onPointerMove(e: PointerEvent) {
  const s = dragState.value
  if (!s) return
  const w = windows.find((x) => x.id === s.id)
  if (!w) return
  const dx = e.clientX - s.startX
  const dy = e.clientY - s.startY
  if (s.mode === 'move') {
    w.x = Math.max(0, s.origX + dx)
    w.y = Math.max(0, s.origY + dy)
  } else {
    w.w = Math.max(240, s.origW + dx)
    w.h = Math.max(160, s.origH + dy)
  }
}

function onPointerUp() {
  dragState.value = null
}

function addWindow() {
  // Default to first non-workbench module to avoid self-recursion.
  const first = moduleEntries.find((e) => e.name !== 'workbench')
  if (!first) return
  windows.push({
    id: first.name + '-' + Date.now(),
    title: first.title + ' (copy)',
    src: first.external ?? first.path ?? '/',
    x: 60 + windows.length * 24,
    y: 60 + windows.length * 24,
    w: 720,
    h: 480,
    z: ++zCounter,
  })
}

function closeWindow(id: string) {
  const i = windows.findIndex((x) => x.id === id)
  if (i >= 0) windows.splice(i, 1)
}
</script>

<template>
  <div class="workbench" @pointermove="onPointerMove" @pointerup="onPointerUp">
    <div class="workbench-toolbar">
      <button type="button" @click="addWindow">+ new window</button>
      <span class="toolbar-hint">
        drag header to move · drag bottom-right corner to resize · click any window to bring to front
      </span>
    </div>

    <div v-if="windows.length === 0" class="empty">
      no modules registered — add entries to <code>moduleEntries</code> in <code>router.ts</code>
    </div>

    <div
      v-for="w in windows"
      :key="w.id"
      class="window"
      :style="{
        left: w.x + 'px',
        top: w.y + 'px',
        width: w.w + 'px',
        height: w.h + 'px',
        zIndex: w.z,
      }"
      @pointerdown="bringToFront(w)"
    >
      <div class="window-header" @pointerdown="onHeaderPointerDown($event, w)">
        <span class="window-title">{{ w.title }}</span>
        <span class="window-src">{{ w.src }}</span>
        <button type="button" class="close" @pointerdown.stop @click="closeWindow(w.id)">×</button>
      </div>
      <iframe
        :src="w.src"
        :title="w.title"
        class="window-frame"
        allow="cross-origin-isolated; shared-array-buffer"
      ></iframe>
      <div class="resize-handle" @pointerdown="onResizePointerDown($event, w)"></div>
    </div>
  </div>
</template>

<style scoped>
.workbench {
  position: fixed;
  inset: 42px 0 0 0; /* leaves room for hub top-nav */
  overflow: hidden;
  background: #0f0f14;
  user-select: none;
}

.workbench-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 16px;
  background: #1a1a1f;
  border-bottom: 1px solid #403d52;
  position: relative;
  z-index: 10000;
}

.toolbar-hint {
  color: #6e6a86;
  font-size: 12px;
}

.empty {
  padding: 40px;
  color: #6e6a86;
  text-align: center;
}

.window {
  position: absolute;
  background: #1a1a1f;
  border: 1px solid #403d52;
  border-radius: 4px;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.4);
  display: flex;
  flex-direction: column;
  min-width: 240px;
  min-height: 160px;
}

.window-header {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 6px 10px;
  background: #2a2a33;
  border-bottom: 1px solid #403d52;
  cursor: grab;
  user-select: none;
}

.window-header:active {
  cursor: grabbing;
}

.window-title {
  color: #c4a7e7;
  font-weight: 600;
  font-size: 13px;
}

.window-src {
  color: #6e6a86;
  font-size: 11px;
  font-family: ui-monospace, monospace;
  flex: 1;
}

.close {
  background: transparent;
  border: none;
  color: #6e6a86;
  font-size: 18px;
  line-height: 1;
  padding: 0 6px;
  cursor: pointer;
}

.close:hover {
  color: #eb6f92;
}

.window-frame {
  flex: 1;
  border: none;
  background: #1a1a1f;
}

.resize-handle {
  position: absolute;
  right: 0;
  bottom: 0;
  width: 16px;
  height: 16px;
  cursor: nwse-resize;
  background: linear-gradient(135deg, transparent 50%, #6e6a86 50%);
  border-bottom-right-radius: 4px;
}

code {
  background: #0f0f14;
  padding: 1px 4px;
  border-radius: 2px;
  color: #f6c177;
  font-size: 12px;
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
</style>
