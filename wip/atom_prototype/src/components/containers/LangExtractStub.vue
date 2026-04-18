<script setup lang="ts">
/**
 * Stub for langextract-repurposed shadow-markup container.
 *
 * Real implementation (deferred): given `text` + `annotations` (char-range
 * tagged spans), renders a transparent overlay that moves with the text and
 * surfaces range-tied metadata. See RUNTIME_STACK.md component 4.
 *
 * For now: visualizes what the shape looks like — text with highlighted
 * range segments and tooltip-on-hover for annotation data.
 */
import { computed } from 'vue'

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

const text = computed(() => props.text ?? '')
const annotations = computed(() => props.annotations ?? [])

// Compute non-overlapping segments of the text: either plain or wrapped in a
// highlight for an annotation. Naive O(n*a), fine for prototype.
const segments = computed(() => {
  const source = text.value
  const sorted = [...annotations.value].sort((a, b) => a.start - b.start)
  const out: Array<{ text: string; ann?: Annotation }> = []
  let cursor = 0
  for (const a of sorted) {
    if (a.start > cursor) out.push({ text: source.slice(cursor, a.start) })
    out.push({ text: source.slice(a.start, a.end), ann: a })
    cursor = a.end
  }
  if (cursor < source.length) out.push({ text: source.slice(cursor) })
  return out
})
</script>

<template>
  <div class="langextract-stub">
    <p class="note">
      <strong>langextract shadow-layer stub.</strong> Annotations render as highlighted ranges;
      hover for attributes. Real runtime (range rebasing on text mutation, multiple independent
      layers) is deferred — see <code>RUNTIME_STACK.md</code> component 4.
    </p>

    <div class="surface">
      <template v-for="(seg, i) in segments" :key="i">
        <span v-if="!seg.ann" class="plain">{{ seg.text }}</span>
        <mark
          v-else
          :class="'klass-' + seg.ann.klass"
          :title="JSON.stringify({ klass: seg.ann.klass, ...seg.ann.attributes })"
        >{{ seg.text }}</mark>
      </template>
    </div>

    <details class="raw" v-if="annotations.length">
      <summary>raw annotations ({{ annotations.length }})</summary>
      <pre>{{ JSON.stringify(annotations, null, 2) }}</pre>
    </details>
  </div>
</template>

<style scoped>
.langextract-stub {
  padding: 10px;
  height: 100%;
  box-sizing: border-box;
  overflow: auto;
  background: #1a1a1f;
  color: #e0def4;
  font-size: 13px;
}
.note {
  color: #6e6a86;
  font-size: 11px;
  line-height: 1.4;
  margin: 0 0 10px 0;
}
.surface {
  font-family: ui-monospace, monospace;
  white-space: pre-wrap;
  line-height: 1.6;
  background: #0f0f14;
  padding: 10px;
  border-radius: 4px;
}
.plain { color: #e0def4; }
mark {
  border-radius: 2px;
  padding: 0 2px;
  color: #0f0f14;
  cursor: help;
}
.klass-link { background: #9ccfd8; }
.klass-ref { background: #c4a7e7; }
.klass-ent { background: #f6c177; }
.klass-tag { background: #ebbcba; }
mark { background: #8ec07c; }
.raw {
  margin-top: 10px;
  color: #6e6a86;
}
.raw pre {
  background: #0f0f14;
  padding: 8px;
  border-radius: 3px;
  font-size: 11px;
  color: #f6c177;
  overflow-x: auto;
}
code {
  background: #0f0f14;
  padding: 1px 4px;
  border-radius: 2px;
  color: #f6c177;
}
</style>
