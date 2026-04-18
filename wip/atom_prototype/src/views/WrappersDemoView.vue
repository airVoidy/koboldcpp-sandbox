<script setup lang="ts">
import { onMounted, ref, reactive } from 'vue'
import { AtomRegistry, type AtomRunResult, mkAtom, wrappers } from '../atom'
import {
  autoMountWrapper,
  bridgeWrapper,
  mountManager,
  registerContainer,
  type ContainerSpec,
  type Mounted,
} from '../mount'
import LexicalContainer from '../components/containers/LexicalContainer.vue'
import LangExtractStub from '../components/containers/LangExtractStub.vue'
import WebContainerStub from '../components/containers/WebContainerStub.vue'

// Register container types once per view mount.
registerContainer('lexical', LexicalContainer, 'Lexical')
registerContainer('langextract', LangExtractStub, 'LangExtract shadow')
registerContainer('web-container', WebContainerStub, 'web-container')

const log = ref<AtomRunResult[]>([])
const registry = new AtomRegistry()
registry.onRun((result) => {
  log.value = [result, ...log.value].slice(0, 20)
})

// Wrapper stack: logging → bridging → auto-mount (order matters —
// bridge runs BEFORE auto-mount so the mounter sees transformed specs).
registry.registerWrapper(wrappers.logging('log'))
registry.registerWrapper(
  bridgeWrapper(
    'bash-to-lexical',
    'fake-bash',
    (output) => {
      const o = output as { cmd: string; stdout: string }
      return {
        type: 'lexical',
        id: 'bash-echo-' + Date.now(),
        title: 'Bash stdout → Lexical',
        props: { content: o.stdout, placeholder: 'bash output' },
      } as ContainerSpec
    },
  ),
)
registry.registerWrapper(autoMountWrapper('auto-mount'))

// Atom 1: spawn Lexical with seeded content.
registry.register(
  mkAtom(
    'spawn-lexical',
    [],
    {
      type: 'lambda',
      fn: () => {
        return {
          type: 'lexical',
          id: 'lex-' + Date.now(),
          title: 'Lexical instance',
          props: { content: 'fresh Lexical — edit me', placeholder: 'type here…' },
        } as ContainerSpec
      },
    },
    ['last-spawn'],
    { kind: 'op', tags: ['spawn', 'lexical'] },
  ),
)

// Atom 2: spawn langextract with annotated text.
registry.register(
  mkAtom(
    'spawn-langextract',
    [],
    {
      type: 'lambda',
      fn: () => {
        const text =
          'See the docs at https://example.com/docs (ref: RFC-1234). Lilith and Morgana are demonesses.'
        return {
          type: 'langextract',
          id: 'langext-' + Date.now(),
          title: 'LangExtract overlay',
          props: {
            text,
            annotations: [
              { start: 15, end: 38, klass: 'link', attributes: { href: 'https://example.com/docs' } },
              { start: 45, end: 54, klass: 'ref', attributes: { citation: 'RFC-1234' } },
              { start: 57, end: 63, klass: 'ent', attributes: { role: 'demoness' } },
              { start: 68, end: 75, klass: 'ent', attributes: { role: 'demoness' } },
            ],
          },
        } as ContainerSpec
      },
    },
    ['last-spawn'],
    { kind: 'op', tags: ['spawn', 'langextract'] },
  ),
)

// Atom 3: "fake-bash" — simulates a bash command; bridge wrapper transforms
// its output into a Lexical spec; auto-mount renders it. Demonstrates
// cross-type pipeline: one atom output → different container type.
registry.register(
  mkAtom(
    'fake-bash',
    ['cmd'],
    {
      type: 'lambda',
      fn: async (input) => {
        const cmd = String(input)
        // Pretend to execute.
        await new Promise((r) => setTimeout(r, 40))
        const stdout =
          cmd === 'ls'
            ? 'atom.ts\nmount.ts\nrouter.ts\nviews/\ncomponents/'
            : cmd === 'date'
              ? new Date().toISOString()
              : `echo from "${cmd}"`
        return { cmd, stdout, exitCode: 0 }
      },
    },
    ['last-bash-result'],
    { kind: 'op', tags: ['exec', 'bash'] },
  ),
)

// Atom 4: spawn the web-container stub directly (no bridge).
registry.register(
  mkAtom(
    'spawn-web-container',
    [],
    {
      type: 'lambda',
      fn: () => {
        return {
          type: 'web-container',
          id: 'wc-' + Date.now(),
          title: 'web-container view',
          props: {
            cmd: 'ls -la',
            stdout: 'drwxr-xr-x  atom.ts mount.ts router.ts\ndrwxr-xr-x  views/ components/\n',
            exitCode: 0,
          },
        } as ContainerSpec
      },
    },
    ['last-spawn'],
    { kind: 'op', tags: ['spawn', 'web-container'] },
  ),
)

function runSpawnLexical() {
  void registry.run('spawn-lexical')
}
function runSpawnLangExtract() {
  void registry.run('spawn-langextract')
}
function runSpawnWebContainer() {
  void registry.run('spawn-web-container')
}
function runFakeBash(cmd: string) {
  registry.setValue('cmd', cmd)
  void registry.run('fake-bash')
}

// Drag/resize for mounted cells (copied pattern from WorkbenchView).
let zCounter = 20
function bringToFront(m: Mounted) {
  m.z = ++zCounter
  mountManager.focus(m.id)
}
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

function onHeaderDown(e: PointerEvent, m: Mounted) {
  bringToFront(m)
  drag.id = m.id
  drag.mode = 'move'
  drag.startX = e.clientX
  drag.startY = e.clientY
  drag.origX = m.x
  drag.origY = m.y
  drag.origW = m.w
  drag.origH = m.h
  ;(e.currentTarget as HTMLElement).setPointerCapture(e.pointerId)
}
function onResizeDown(e: PointerEvent, m: Mounted) {
  bringToFront(m)
  drag.id = m.id
  drag.mode = 'resize'
  drag.startX = e.clientX
  drag.startY = e.clientY
  drag.origX = m.x
  drag.origY = m.y
  drag.origW = m.w
  drag.origH = m.h
  ;(e.currentTarget as HTMLElement).setPointerCapture(e.pointerId)
  e.stopPropagation()
}
function onMove(e: PointerEvent) {
  if (!drag.id) return
  const m = mountManager.mounted.find((x) => x.id === drag.id)
  if (!m) return
  const dx = e.clientX - drag.startX
  const dy = e.clientY - drag.startY
  if (drag.mode === 'move') {
    m.x = Math.max(0, drag.origX + dx)
    m.y = Math.max(0, drag.origY + dy)
  } else {
    m.w = Math.max(240, drag.origW + dx)
    m.h = Math.max(160, drag.origH + dy)
  }
}
function onUp() {
  drag.id = null
}

onMounted(() => {
  // Seed a couple of default containers so the page isn't empty on load.
  runSpawnLexical()
  runSpawnLangExtract()
})
</script>

<template>
  <div class="container">
    <h1>Cross-Type Wrappers + Container Mounting</h1>
    <p class="subtitle">
      Atom outputs → <code>ContainerSpec</code> → auto-mount wrapper → live Vue component
      in a floating cell. Bridge wrappers transform one atom's output into a different
      container type (e.g. bash stdout → Lexical view). Multiple container types coexist
      on the same page with shared reactivity.
    </p>

    <div class="controls">
      <button @click="runSpawnLexical">Spawn Lexical</button>
      <button @click="runSpawnLangExtract">Spawn LangExtract overlay</button>
      <button @click="runSpawnWebContainer">Spawn web-container stub</button>
      <span class="divider" />
      <button @click="runFakeBash('ls')">fake-bash: ls (bridge → Lexical)</button>
      <button @click="runFakeBash('date')">fake-bash: date (bridge → Lexical)</button>
      <span class="divider" />
      <button @click="mountManager.clear()">clear all</button>
    </div>

    <div class="mount-area" @pointermove="onMove" @pointerup="onUp">
      <div
        v-for="m in mountManager.mounted"
        :key="m.id"
        class="cell"
        :style="{ left: m.x + 'px', top: m.y + 'px', width: m.w + 'px', height: m.h + 'px', zIndex: m.z }"
        @pointerdown="bringToFront(m)"
      >
        <div class="cell-header" @pointerdown="onHeaderDown($event, m)">
          <span class="cell-type">{{ m.type }}</span>
          <span class="cell-title">{{ m.title }}</span>
          <span class="cell-id">{{ m.id }}</span>
          <button class="close" @click.stop="mountManager.close(m.id)">×</button>
        </div>
        <div class="cell-body">
          <component :is="m.component" v-bind="m.props" />
        </div>
        <div class="resize-handle" @pointerdown="onResizeDown($event, m)"></div>
      </div>
      <div v-if="mountManager.mounted.length === 0" class="empty">
        no containers mounted — click a button above
      </div>
    </div>

    <details class="log-details">
      <summary>atom run log ({{ log.length }})</summary>
      <pre class="log">
        <div v-for="(entry, i) in log" :key="i" class="log-entry">
          <strong>{{ entry.atomId }}</strong> · {{ entry.durationMs.toFixed(2) }}ms
          {{ '\n  output: ' }}{{ JSON.stringify(entry.output) }}
          <template v-if="entry.trace">
            {{ '\n  trace:' }}
            <template v-for="(t, j) in entry.trace" :key="j">
              {{ '\n    ' }}[{{ t.tAt.toFixed(2) }}ms] <em>{{ t.wrapperId }}</em> · {{ t.event }}{{ t.note != null ? ' · ' + JSON.stringify(t.note) : '' }}
            </template>
          </template>
        </div>
      </pre>
    </details>
  </div>
</template>

<style scoped>
.controls {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin: 12px 0;
  align-items: center;
}
.divider {
  border-left: 1px solid #403d52;
  height: 20px;
}
button {
  background: #403d52;
  color: #e0def4;
  border: 1px solid #6e6a86;
  padding: 6px 12px;
  border-radius: 4px;
  cursor: pointer;
  font-family: inherit;
  font-size: 13px;
}
button:hover { background: #524f67; }

.mount-area {
  position: relative;
  min-height: 500px;
  background: #0f0f14;
  border: 1px dashed #403d52;
  border-radius: 4px;
  margin: 8px 0;
  overflow: hidden;
}
.empty {
  position: absolute;
  inset: 0;
  display: grid;
  place-items: center;
  color: #6e6a86;
}
.cell {
  position: absolute;
  background: #1a1a1f;
  border: 1px solid #403d52;
  border-radius: 4px;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.4);
  display: flex;
  flex-direction: column;
}
.cell-header {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 5px 10px;
  background: #2a2a33;
  border-bottom: 1px solid #403d52;
  cursor: grab;
  font-size: 12px;
}
.cell-type {
  color: #c4a7e7;
  font-weight: 600;
}
.cell-title { color: #e0def4; flex: 0; }
.cell-id {
  color: #6e6a86;
  font-family: ui-monospace, monospace;
  font-size: 10px;
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.close {
  background: transparent;
  border: none;
  color: #6e6a86;
  font-size: 16px;
  padding: 0 4px;
  cursor: pointer;
}
.close:hover { color: #eb6f92; }
.cell-body {
  flex: 1;
  overflow: hidden;
}
.resize-handle {
  position: absolute;
  right: 0;
  bottom: 0;
  width: 14px;
  height: 14px;
  cursor: nwse-resize;
  background: linear-gradient(135deg, transparent 50%, #6e6a86 50%);
}

.log-details {
  margin-top: 16px;
}
.log-details summary {
  cursor: pointer;
  color: #c4a7e7;
  font-size: 12px;
}
pre.log {
  background: #0f0f14;
  color: #f6c177;
  padding: 10px;
  border-radius: 4px;
  font-size: 11px;
  max-height: 200px;
  overflow-y: auto;
}
.log-entry { color: #ebbcba; }
.log-entry + .log-entry {
  margin-top: 6px;
  padding-top: 6px;
  border-top: 1px solid #2a2a33;
}
em { color: #c4a7e7; font-style: normal; }
code {
  background: #0f0f14;
  padding: 1px 4px;
  border-radius: 2px;
  color: #f6c177;
  font-size: 12px;
}
</style>
