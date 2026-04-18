<script setup lang="ts">
import { computed, ref } from 'vue'
import {
  makeLangScope,
  spanProjections,
  type AnnotatedDocument,
} from '../langextract'

/**
 * Demonstrates langextract wrapped in our architecture:
 *   - atomic()  per span
 *   - list()    per extraction_class (detached per-class lists)
 *   - Virtual Projection: text / range / klass / attrs / withContext / uri
 *   - Hierarchical LangScope (parent chain), namescope registering each span
 *
 * Inspired by LangChain's nested-run scope pattern: outer scope ≡ orchestrator,
 * child scopes ≡ sub-tasks. `lookupAlias` walks up the parent chain.
 */

const sampleDoc: AnnotatedDocument = {
  document_id: 'doc-primary',
  text: 'See the docs at https://example.com/docs (ref: RFC-1234). Lilith and Morgana are demonesses. Project Alpha ships Monday.',
  extractions: [
    { extraction_class: 'link', extraction_text: 'https://example.com/docs', char_interval: { start_pos: 16, end_pos: 40 }, attributes: { href: 'https://example.com/docs' } },
    { extraction_class: 'ref', extraction_text: 'RFC-1234', char_interval: { start_pos: 47, end_pos: 55 }, attributes: { citation: 'RFC-1234' } },
    { extraction_class: 'ent', extraction_text: 'Lilith', char_interval: { start_pos: 58, end_pos: 64 }, attributes: { role: 'demoness' } },
    { extraction_class: 'ent', extraction_text: 'Morgana', char_interval: { start_pos: 69, end_pos: 76 }, attributes: { role: 'demoness' } },
    { extraction_class: 'project', extraction_text: 'Project Alpha', char_interval: { start_pos: 94, end_pos: 107 }, attributes: { status: 'active' } },
  ],
}

const childDoc: AnnotatedDocument = {
  document_id: 'doc-followup',
  text: 'Meeting notes: Lilith approves.',
  extractions: [
    { extraction_class: 'ent', extraction_text: 'Lilith', char_interval: { start_pos: 15, end_pos: 21 }, attributes: { role: 'approver' } },
  ],
}

const outerScope = makeLangScope('outer', sampleDoc, { metadata: { model: 'stub-v0', runId: 'run-01' } })
const innerScope = outerScope.childScope('inner', childDoc, { model: 'stub-v0', runId: 'run-02' })

const activeScope = ref<'outer' | 'inner'>('outer')
const scope = computed(() => (activeScope.value === 'outer' ? outerScope : innerScope))

// For visualizing the annotated text with highlighted ranges.
const highlightedSegments = computed(() => {
  const s = scope.value
  const sorted = [...s.doc.extractions].sort((a, b) => a.char_interval.start_pos - b.char_interval.start_pos)
  const out: Array<{ text: string; span?: typeof sorted[number] }> = []
  let cursor = 0
  for (const ext of sorted) {
    if (ext.char_interval.start_pos > cursor) {
      out.push({ text: s.doc.text.slice(cursor, ext.char_interval.start_pos) })
    }
    out.push({ text: s.doc.text.slice(ext.char_interval.start_pos, ext.char_interval.end_pos), span: ext })
    cursor = ext.char_interval.end_pos
  }
  if (cursor < s.doc.text.length) out.push({ text: s.doc.text.slice(cursor) })
  return out
})

const aliasLookup = ref('first:project')
const aliasResult = computed(() => scope.value.lookupAlias(aliasLookup.value))
</script>

<template>
  <div class="container">
    <h1>LangExtract — atomic() + list() + Virtual Projection + LangScope</h1>
    <p class="subtitle">
      Each span wrapped in <code>atomic()</code>. Document grouped по extraction_class
      into detached <code>NestedAtomicList</code>s. Namescope registers each span as a
      virtual type + shared <code>first:&lt;class&gt;</code> aliases. Scopes nest
      hierarchically — <code>lookupAlias</code> walks parent chain (LangChain-style).
    </p>

    <div class="scope-tabs">
      <button :class="{ active: activeScope === 'outer' }" @click="activeScope = 'outer'">
        outer scope ({{ outerScope.id }})
      </button>
      <button :class="{ active: activeScope === 'inner' }" @click="activeScope = 'inner'">
        inner scope (child of outer, {{ innerScope.id }})
      </button>
      <span class="chain-label">chain: {{ scope.chain().map((s) => s.id).join(' → ') }}</span>
    </div>

    <section class="panel">
      <h2>Document <span class="dim">{{ scope.doc.document_id }}</span></h2>
      <div class="text-with-highlights">
        <template v-for="(seg, i) in highlightedSegments" :key="i">
          <span v-if="!seg.span">{{ seg.text }}</span>
          <mark v-else :class="'kls-' + seg.span.extraction_class" :title="JSON.stringify(seg.span.attributes ?? {})">
            {{ seg.text }}
            <sup class="mark-label">{{ seg.span.extraction_class }}</sup>
          </mark>
        </template>
      </div>
    </section>

    <div class="grid">
      <section class="panel">
        <h2>Detached per-class lists <span class="dim">(groupByClass)</span></h2>
        <div v-for="(list, klass) in scope.lists" :key="klass" class="list-group">
          <div class="list-head">
            <strong :class="'kls-' + klass">{{ klass }}</strong>
            <span class="dim">· {{ list.size }} span{{ list.size === 1 ? '' : 's' }}</span>
          </div>
          <ul class="spans">
            <li v-for="[key, span] in list.entries()" :key="key">
              <div class="span-row">
                <span class="span-text">{{ span.extraction_text }}</span>
                <code class="span-range">[{{ span.char_interval.start_pos }}–{{ span.char_interval.end_pos }}]</code>
              </div>
              <details class="span-details">
                <summary>projections</summary>
                <div class="proj-row"><span class="pk">text:</span> <code>{{ spanProjections.text(span) }}</code></div>
                <div class="proj-row"><span class="pk">range:</span> <code>{{ JSON.stringify(spanProjections.range(span)) }}</code></div>
                <div class="proj-row"><span class="pk">klass:</span> <code>{{ spanProjections.klass(span) }}</code></div>
                <div class="proj-row"><span class="pk">attrs:</span> <code>{{ JSON.stringify(spanProjections.attrs(span)) }}</code></div>
                <div class="proj-row"><span class="pk">ctx:</span> <code>{{ spanProjections.withContext(span, scope.doc, 10) }}</code></div>
                <div class="proj-row"><span class="pk">uri:</span> <code>{{ spanProjections.uri(span, scope.id) }}</code></div>
              </details>
            </li>
          </ul>
        </div>
      </section>

      <section class="panel">
        <h2>Namescope <span class="dim">({{ scope.namescope.size() }} types, {{ scope.namescope.sharedAliases().length }} shared aliases)</span></h2>
        <div class="subpanel">
          <div class="subpanel-label">Shared aliases</div>
          <div v-for="[name, hash] in scope.namescope.sharedAliases()" :key="name" class="alias-row">
            <span class="alias-name">{{ name }}</span>
            <span class="arrow">→</span>
            <code class="alias-hash">{{ hash.slice(0, 48) }}{{ hash.length > 48 ? '…' : '' }}</code>
          </div>
        </div>

        <div class="subpanel">
          <div class="subpanel-label">Lookup (walks parent chain)</div>
          <div class="lookup-row">
            <input v-model="aliasLookup" placeholder="first:project" />
            <button @click="aliasLookup = 'first:project'">first:project</button>
            <button @click="aliasLookup = 'first:ent'">first:ent</button>
            <button @click="aliasLookup = 'first:link'">first:link</button>
          </div>
          <div class="lookup-result" v-if="aliasResult">
            <div><strong>found in scope:</strong></div>
            <code>{{ JSON.stringify(aliasResult, null, 2) }}</code>
          </div>
          <div class="lookup-result empty" v-else>
            <em>no match in chain: {{ scope.chain().map((s) => s.id).join(' → ') }}</em>
          </div>
        </div>

        <div class="subpanel">
          <div class="subpanel-label">Metadata</div>
          <pre class="meta">{{ JSON.stringify(scope.metadata, null, 2) }}</pre>
        </div>
      </section>
    </div>
  </div>
</template>

<style scoped>
.scope-tabs {
  display: flex;
  gap: 6px;
  align-items: center;
  margin: 12px 0;
}
.scope-tabs button {
  background: #403d52;
  color: #e0def4;
  border: 1px solid #6e6a86;
  padding: 6px 12px;
  border-radius: 3px;
  cursor: pointer;
  font-size: 12px;
}
.scope-tabs button.active {
  background: #9ccfd8;
  color: #0f0f14;
  border-color: #9ccfd8;
}
.chain-label {
  color: #6e6a86;
  font-size: 12px;
  font-family: ui-monospace, monospace;
  margin-left: 10px;
}

.panel {
  background: #1a1a1f;
  border: 1px solid #403d52;
  border-radius: 6px;
  padding: 14px;
  margin-bottom: 14px;
}
.panel h2 {
  color: #c4a7e7;
  margin: 0 0 10px 0;
  font-size: 16px;
}
.dim {
  color: #6e6a86;
  font-size: 12px;
  font-weight: normal;
}

.text-with-highlights {
  background: #0f0f14;
  padding: 12px;
  border-radius: 4px;
  line-height: 1.8;
  font-family: ui-monospace, monospace;
  font-size: 13px;
  color: #e0def4;
}
mark {
  border-radius: 2px;
  padding: 0 3px;
  color: #0f0f14;
  position: relative;
}
.kls-link { background: #9ccfd8; }
.kls-ref { background: #c4a7e7; }
.kls-ent { background: #f6c177; }
.kls-project { background: #8ec07c; }
.mark-label {
  font-size: 9px;
  color: #0f0f14;
  opacity: 0.7;
  margin-left: 2px;
}

.grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 14px;
}
.list-group {
  border: 1px solid #2a2a33;
  border-radius: 4px;
  padding: 8px 10px;
  margin-bottom: 8px;
  background: #0f0f14;
}
.list-head strong {
  padding: 2px 6px;
  border-radius: 2px;
  color: #0f0f14;
  font-size: 11px;
  font-family: ui-monospace, monospace;
}
.spans {
  list-style: none;
  padding: 0;
  margin: 6px 0 0 0;
}
.spans li {
  padding: 4px 0;
  border-bottom: 1px dashed #2a2a33;
  font-size: 12px;
}
.spans li:last-child {
  border-bottom: none;
}
.span-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.span-text {
  color: #e0def4;
}
.span-range {
  color: #6e6a86;
  font-family: ui-monospace, monospace;
  font-size: 11px;
}
.span-details {
  margin-top: 4px;
}
.span-details summary {
  cursor: pointer;
  color: #6e6a86;
  font-size: 11px;
}
.proj-row {
  padding: 2px 0;
  font-size: 11px;
}
.pk {
  color: #c4a7e7;
  display: inline-block;
  width: 50px;
}
.proj-row code {
  color: #f6c177;
  font-size: 11px;
  word-break: break-all;
}

.subpanel {
  margin-bottom: 10px;
  padding-bottom: 10px;
  border-bottom: 1px solid #2a2a33;
}
.subpanel:last-child {
  border-bottom: none;
}
.subpanel-label {
  color: #6e6a86;
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.1em;
  margin-bottom: 6px;
}
.alias-row {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  font-family: ui-monospace, monospace;
  padding: 2px 0;
}
.alias-name {
  color: #8ec07c;
  min-width: 100px;
}
.arrow {
  color: #6e6a86;
}
.alias-hash {
  color: #ebbcba;
  font-size: 11px;
}

.lookup-row {
  display: flex;
  gap: 6px;
  margin-bottom: 6px;
  align-items: center;
}
.lookup-row input {
  background: #0f0f14;
  color: #e0def4;
  border: 1px solid #403d52;
  padding: 4px 8px;
  border-radius: 3px;
  font-family: ui-monospace, monospace;
  font-size: 12px;
  flex: 1;
}
.lookup-row button {
  background: #403d52;
  color: #e0def4;
  border: 1px solid #6e6a86;
  padding: 3px 8px;
  border-radius: 3px;
  cursor: pointer;
  font-size: 11px;
  font-family: ui-monospace, monospace;
}
.lookup-row button:hover {
  background: #524f67;
}
.lookup-result {
  background: #0f0f14;
  padding: 8px;
  border-radius: 3px;
  font-size: 12px;
}
.lookup-result.empty em {
  color: #6e6a86;
}
.lookup-result code {
  color: #f6c177;
  font-size: 11px;
  display: block;
  white-space: pre-wrap;
}
pre.meta {
  background: #0f0f14;
  color: #f6c177;
  padding: 8px;
  border-radius: 3px;
  font-size: 11px;
  margin: 0;
}
code {
  background: transparent;
  font-family: ui-monospace, monospace;
}
</style>
