<script setup lang="ts">
/**
 * Interactive langextract-style container.
 *
 * Lets you edit the underlying text and add/remove character-range
 * annotations live. Renders highlighted segments in real time + the
 * annotation list as a table. Not a full rebase-on-edit implementation
 * (ranges don't auto-adjust on text mutation — they stay pointing at the
 * original positions), but the surface is real and usable.
 *
 * Selection → click `annotate selection` → the current text selection
 * becomes a new annotation with the class you chose.
 */

import { computed, ref } from 'vue'

interface Annotation {
  start: number
  end: number
  klass: string
  attributes?: Record<string, unknown>
}

const props = defineProps<{
  text?: string
  annotations?: Annotation[]
}>()

const text = ref(props.text ?? '')
const annotations = ref<Annotation[]>(
  (props.annotations ?? []).map((a) => ({ ...a })),
)

const klassInput = ref('tag')
const renderRoot = ref<HTMLDivElement | null>(null)

const segments = computed(() => {
  const source = text.value
  const sorted = [...annotations.value]
    .filter((a) => a.start >= 0 && a.end <= source.length && a.start < a.end)
    .sort((a, b) => a.start - b.start)
  const out: Array<{ text: string; ann?: Annotation }> = []
  let cursor = 0
  for (const a of sorted) {
    if (a.start < cursor) continue // skip overlaps (naive)
    if (a.start > cursor) out.push({ text: source.slice(cursor, a.start) })
    out.push({ text: source.slice(a.start, a.end), ann: a })
    cursor = a.end
  }
  if (cursor < source.length) out.push({ text: source.slice(cursor) })
  return out
})

function addAnnotationFromSelection() {
  const selection = window.getSelection()
  if (!selection || selection.rangeCount === 0) return
  const range = selection.getRangeAt(0)
  if (!renderRoot.value) return
  if (!renderRoot.value.contains(range.commonAncestorContainer)) {
    // selection is outside our render root — ignore
    return
  }

  // Compute character offsets relative to the full text.
  const preRange = range.cloneRange()
  preRange.selectNodeContents(renderRoot.value)
  preRange.setEnd(range.startContainer, range.startOffset)
  const start = preRange.toString().length
  const end = start + range.toString().length
  if (start >= end) return

  annotations.value.push({ start, end, klass: klassInput.value })
  selection.removeAllRanges()
}

function removeAnnotation(index: number) {
  annotations.value.splice(index, 1)
}

function resetAnnotations() {
  annotations.value = []
}
</script>

<template>
  <div class="langextract">
    <div class="panel">
      <label class="label">source text (editable)</label>
      <textarea v-model="text" class="source" spellcheck="true" />
    </div>

    <div class="panel">
      <label class="label">preview with highlights (select text → annotate)</label>
      <div
        ref="renderRoot"
        class="render"
        @pointerdown.stop
        @mousedown.stop
      >
        <template v-for="(seg, i) in segments" :key="i">
          <span v-if="!seg.ann" class="plain">{{ seg.text }}</span>
          <mark
            v-else
            :class="'klass-' + seg.ann.klass"
            :title="JSON.stringify({ klass: seg.ann.klass, start: seg.ann.start, end: seg.ann.end, ...(seg.ann.attributes ?? {}) })"
          >{{ seg.text }}</mark>
        </template>
      </div>
      <div class="selection-row">
        <input v-model="klassInput" type="text" class="klass-input" placeholder="class name" />
        <button @click="addAnnotationFromSelection" type="button">annotate selection</button>
      </div>
    </div>

    <div class="panel">
      <label class="label">annotations ({{ annotations.length }})</label>
      <table v-if="annotations.length > 0" class="ann-table">
        <thead>
          <tr>
            <th>class</th>
            <th>range</th>
            <th>excerpt</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(a, i) in annotations" :key="i">
            <td><span class="chip" :class="'klass-' + a.klass">{{ a.klass }}</span></td>
            <td><code>{{ a.start }}–{{ a.end }}</code></td>
            <td><code>{{ text.slice(a.start, a.end) }}</code></td>
            <td><button class="mini" @click="removeAnnotation(i)">×</button></td>
          </tr>
        </tbody>
      </table>
      <p v-else class="empty">[ no annotations — select text above and click "annotate selection" ]</p>
      <button v-if="annotations.length > 0" class="mini reset" @click="resetAnnotations">reset all</button>
    </div>
  </div>
</template>

<style scoped>
.langextract {
  padding: 10px;
  height: 100%;
  box-sizing: border-box;
  overflow: auto;
  background: #1a1a1f;
  color: #e0def4;
  font-size: 13px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.panel {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.label {
  color: #6e6a86;
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.source {
  background: #0f0f14;
  color: #e0def4;
  border: 1px solid #403d52;
  border-radius: 4px;
  padding: 8px;
  font-family: ui-monospace, monospace;
  font-size: 12px;
  line-height: 1.5;
  min-height: 70px;
  resize: vertical;
}

.source:focus {
  outline: none;
  border-color: rgba(196, 167, 231, 0.5);
}

.render {
  font-family: ui-monospace, monospace;
  white-space: pre-wrap;
  line-height: 1.6;
  background: #0f0f14;
  padding: 10px;
  border-radius: 4px;
  user-select: text;
  cursor: text;
  min-height: 50px;
}

.plain {
  color: #e0def4;
}

mark {
  border-radius: 2px;
  padding: 0 2px;
  color: #0f0f14;
  cursor: help;
}

.klass-link {
  background: #9ccfd8;
}
.klass-ref {
  background: #c4a7e7;
}
.klass-ent {
  background: #f6c177;
}
.klass-tag {
  background: #ebbcba;
}
mark {
  background: #8ec07c;
}

.selection-row {
  display: flex;
  gap: 6px;
  margin-top: 4px;
}

.klass-input {
  flex: 1;
  background: #0f0f14;
  color: #e0def4;
  border: 1px solid #403d52;
  border-radius: 3px;
  padding: 4px 8px;
  font-family: ui-monospace, monospace;
  font-size: 12px;
}

.klass-input:focus {
  outline: none;
  border-color: rgba(196, 167, 231, 0.5);
}

button {
  background: #403d52;
  color: #e0def4;
  border: 1px solid #6e6a86;
  padding: 4px 10px;
  border-radius: 3px;
  cursor: pointer;
  font-family: inherit;
  font-size: 12px;
}

button:hover {
  background: #524f67;
}

.mini {
  padding: 2px 6px;
  font-size: 11px;
}

.reset {
  margin-top: 6px;
  align-self: flex-start;
}

.ann-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
}

.ann-table th,
.ann-table td {
  text-align: left;
  padding: 4px 6px;
  border-bottom: 1px solid #2a2a33;
  vertical-align: middle;
}

.ann-table th {
  color: #6e6a86;
  font-weight: normal;
}

.chip {
  display: inline-block;
  padding: 0 6px;
  border-radius: 2px;
  color: #0f0f14;
  font-size: 11px;
}

.empty {
  color: #6e6a86;
  font-style: italic;
  font-size: 11px;
  margin: 4px 0;
}

code {
  background: #0f0f14;
  padding: 1px 4px;
  border-radius: 2px;
  color: #f6c177;
  font-size: 11px;
}
</style>
