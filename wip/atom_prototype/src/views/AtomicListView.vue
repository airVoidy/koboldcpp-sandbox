<script setup lang="ts">
import { computed, ref } from 'vue'
import {
  ArrayAtomicList,
  NestedAtomicList,
  arrayList,
  nestedList,
  computeAtomicHash,
} from '../atomic-list'

/**
 * Side-by-side playground for the two list variants.
 * Same input → two representations. Add/remove items, see structural dedup
 * on the nested side, inspect the composed hash (schema | value) per entry.
 */

// Start seeded so the page isn't empty on first load.
const arr = ref<ArrayAtomicList<unknown>>(
  arrayList<unknown>([
    { name: 'alice', age: 30 },
    { name: 'bob', age: 25 },
    42,
    'hello',
  ]),
)

const nst = ref<NestedAtomicList<unknown>>(
  nestedList<unknown>([
    { name: 'alice', age: 30 },
    { name: 'bob', age: 25 },
    42,
    'hello',
  ]),
)

const inputText = ref('{"name":"carol","age":28}')
const typeLabel = ref('')

function parseInput(): unknown {
  const raw = inputText.value.trim()
  if (raw === '') return raw
  try {
    return JSON.parse(raw)
  } catch {
    return raw // treat as string literal on parse failure
  }
}

function addToBoth() {
  const v = parseInput()
  arr.value.add(v)
  if (typeLabel.value) {
    nst.value.add(v, typeLabel.value)
  } else {
    nst.value.add(v)
  }
  // Force reactivity (mutating internal state of class instances).
  arr.value = Object.assign(Object.create(Object.getPrototypeOf(arr.value)), arr.value)
  nst.value = Object.assign(Object.create(Object.getPrototypeOf(nst.value)), nst.value)
}

function clearBoth() {
  arr.value.clear()
  nst.value.clear()
  arr.value = Object.assign(Object.create(Object.getPrototypeOf(arr.value)), arr.value)
  nst.value = Object.assign(Object.create(Object.getPrototypeOf(nst.value)), nst.value)
}

function removeArrAt(i: number) {
  arr.value.remove(i)
  arr.value = Object.assign(Object.create(Object.getPrototypeOf(arr.value)), arr.value)
}

function removeNstAt(key: string) {
  nst.value.remove(key)
  nst.value = Object.assign(Object.create(Object.getPrototypeOf(nst.value)), nst.value)
}

// Live preview of the hash that would be computed for the input.
const previewHash = computed(() => {
  const v = parseInput()
  return computeAtomicHash(v, typeLabel.value || undefined)
})

const arrEntries = computed(() => arr.value.entries() as Array<[number, unknown]>)
const nstEntries = computed(
  () => nst.value.entries().map(([k, v]) => [k, v, nst.value.hashOf(k)] as [string, unknown, ReturnType<typeof computeAtomicHash> | undefined]),
)
</script>

<template>
  <div class="container">
    <h1>AtomicList — Array vs Nested</h1>
    <p class="subtitle">
      Same items, two representations. Array form is positional; Nested form
      keys each entry by a composite hash (<code>schema | value</code>). Adding
      a structurally-identical value to Nested dedupes to the same slot; to
      Array it appends. See <code>src/atomic-list.ts</code>.
    </p>

    <section class="input-panel">
      <label>
        Input (JSON or raw string):
        <input v-model="inputText" placeholder='e.g. {"n":1} or "hello" or 42' />
      </label>
      <label>
        Custom fieldValueType (optional):
        <input v-model="typeLabel" placeholder="e.g. score (overrides typeof)" />
      </label>
      <button @click="addToBoth">add to both</button>
      <button @click="clearBoth">clear both</button>

      <div class="preview">
        <strong>preview hash for input:</strong>
        <div><span class="pk">schema:</span> <code>{{ previewHash.schemaPart }}</code></div>
        <div><span class="pk">value: </span> <code>{{ previewHash.valuePart }}</code></div>
        <div><span class="pk">full:  </span> <code>{{ previewHash.full }}</code></div>
      </div>
    </section>

    <div class="grid">
      <section class="panel">
        <h2>ArrayAtomicList <span class="size">{{ arr.size }} items</span></h2>
        <p class="note">positional index, preserves insertion order</p>
        <pre>{{ JSON.stringify(arr.toJSON(), null, 2) }}</pre>
        <ul class="entries">
          <li v-for="[i, v] in arrEntries" :key="i">
            <span class="key">[{{ i }}]</span>
            <code class="val">{{ JSON.stringify(v) }}</code>
            <button class="small" @click="removeArrAt(i)">×</button>
          </li>
        </ul>
      </section>

      <section class="panel">
        <h2>NestedAtomicList <span class="size">{{ nst.size }} entries</span></h2>
        <p class="note">hash-keyed, structural dedup; each entry's key = schema | value</p>
        <pre>{{ JSON.stringify(nst.toJSON(), null, 2) }}</pre>
        <ul class="entries">
          <li v-for="[k, v, h] in nstEntries" :key="k">
            <div class="key-row">
              <span class="key">{{ k }}</span>
              <button class="small" @click="removeNstAt(k)">×</button>
            </div>
            <div class="hash-parts" v-if="h">
              <div><span class="pk">schema:</span> <code>{{ h.schemaPart }}</code></div>
              <div><span class="pk">value: </span> <code>{{ h.valuePart }}</code></div>
            </div>
            <code class="val">{{ JSON.stringify(v) }}</code>
          </li>
        </ul>
      </section>
    </div>
  </div>
</template>

<style scoped>
.input-panel {
  background: #1a1a1f;
  border: 1px solid #403d52;
  border-radius: 6px;
  padding: 14px;
  margin-bottom: 20px;
  display: grid;
  grid-template-columns: 1fr 1fr auto auto;
  gap: 8px;
  align-items: center;
}
.input-panel label {
  display: flex;
  flex-direction: column;
  gap: 2px;
  font-size: 12px;
  color: #6e6a86;
}
.input-panel input {
  background: #0f0f14;
  color: #e0def4;
  border: 1px solid #403d52;
  border-radius: 3px;
  padding: 6px 8px;
  font-family: ui-monospace, monospace;
  font-size: 12px;
}
.preview {
  grid-column: 1 / -1;
  background: #0f0f14;
  padding: 8px;
  border-radius: 4px;
  font-size: 12px;
}
.preview .pk {
  color: #c4a7e7;
  display: inline-block;
  width: 60px;
}
.preview code {
  color: #f6c177;
}

.grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 14px;
}
.panel {
  background: #1a1a1f;
  border: 1px solid #403d52;
  border-radius: 6px;
  padding: 14px;
}
.panel h2 {
  color: #c4a7e7;
  margin: 0 0 4px 0;
  font-size: 16px;
  display: flex;
  align-items: baseline;
  gap: 10px;
}
.panel .size {
  color: #6e6a86;
  font-size: 12px;
  font-weight: normal;
}
.note {
  color: #6e6a86;
  font-size: 12px;
  margin: 0 0 10px 0;
}
pre {
  background: #0f0f14;
  color: #8ec07c;
  padding: 10px;
  border-radius: 4px;
  font-size: 11px;
  max-height: 220px;
  overflow-y: auto;
}
.entries {
  list-style: none;
  padding: 0;
  margin: 12px 0 0 0;
  max-height: 300px;
  overflow-y: auto;
}
.entries li {
  padding: 6px 8px;
  border-bottom: 1px solid #2a2a33;
  font-size: 12px;
}
.entries li:last-child {
  border-bottom: none;
}
.key-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
}
.key {
  color: #9ccfd8;
  font-family: ui-monospace, monospace;
  word-break: break-all;
}
.val {
  color: #e0def4;
  display: block;
  margin-top: 4px;
}
.hash-parts {
  margin-top: 4px;
  font-size: 11px;
}
.hash-parts .pk {
  color: #c4a7e7;
  display: inline-block;
  width: 55px;
}
.hash-parts code {
  color: #f6c177;
}

button {
  background: #403d52;
  color: #e0def4;
  border: 1px solid #6e6a86;
  padding: 6px 12px;
  border-radius: 3px;
  cursor: pointer;
  font-family: inherit;
  font-size: 12px;
}
button:hover {
  background: #524f67;
}
button.small {
  padding: 0 6px;
  font-size: 14px;
  background: transparent;
  color: #6e6a86;
  border-color: transparent;
}
button.small:hover {
  color: #eb6f92;
}
code {
  background: transparent;
  font-family: ui-monospace, monospace;
}
</style>
