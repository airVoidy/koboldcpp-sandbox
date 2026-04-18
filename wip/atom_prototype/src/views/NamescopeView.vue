<script setup lang="ts">
import { computed, reactive, ref, triggerRef } from 'vue'
import { makeNamescope, type VirtualTypeEntry } from '../namescope'

/**
 * Visual playground for the two-detached-list namescope pattern.
 *
 *   LEFT (cells)  ──────▶  RIGHT (namescope = catalog + aliases)
 *
 * One-way: cells hold a ref to the scope; scope never holds refs to cells.
 * Personal aliases are keyed by cellId, so cell isolation is per-id.
 */

const { ns, cell } = makeNamescope()

// Seed a small catalog so the page isn't empty on load.
const seed: VirtualTypeEntry[] = [
  { hash: 'h:msg-alice-1', type: 'msg', payload: { from: 'alice', text: 'hi!' }, tags: ['msg'] },
  { hash: 'h:msg-bob-1', type: 'msg', payload: { from: 'bob', text: 'hey' }, tags: ['msg'] },
  { hash: 'h:channel-general', type: 'channel', payload: { name: 'general' }, tags: ['channel'] },
  { hash: 'h:channel-private', type: 'channel', payload: { name: 'private', locked: true }, tags: ['channel'] },
  { hash: 'h:reaction-thumb', type: 'reaction', payload: { emoji: '👍' }, tags: ['reaction'] },
]
for (const e of seed) ns.registerType(e)

// Cells list — reactive so we can add/remove cells in the UI.
const cellIds = reactive<string[]>(['alice', 'bob'])
const nsRef = ref(0) // tick to force re-read of namescope state in templates

function bump() {
  nsRef.value++
  triggerRef(nsRef)
}

// Seed some initial aliases.
cell('alice').aliasLocal('me', 'h:msg-alice-1')
cell('alice').aliasLocal('home', 'h:channel-general')
cell('bob').aliasLocal('me', 'h:msg-bob-1')
cell('bob').aliasLocal('home', 'h:channel-private')
cell('alice').aliasShared('thumb', 'h:reaction-thumb') // visible to all
bump()

/* catalog editor */
const newHash = ref('')
const newType = ref('msg')
const newPayload = ref('{"note":"..."}')

function addType() {
  if (!newHash.value) return
  try {
    ns.registerType({
      hash: newHash.value,
      type: newType.value,
      payload: JSON.parse(newPayload.value || 'null'),
    })
    newHash.value = ''
  } catch (e) {
    alert('invalid JSON payload: ' + (e as Error).message)
  }
  bump()
}

function removeType(hash: string) {
  ns.unregisterType(hash)
  bump()
}

/* cell + alias editor */
const newCellId = ref('')
function addCell() {
  if (!newCellId.value) return
  if (!cellIds.includes(newCellId.value)) cellIds.push(newCellId.value)
  newCellId.value = ''
}
function removeCell(id: string) {
  const i = cellIds.indexOf(id)
  if (i >= 0) cellIds.splice(i, 1)
  ns.forgetCell(id)
  bump()
}

const aliasCellId = ref('alice')
const aliasName = ref('')
const aliasHash = ref('')
const aliasKind = ref<'personal' | 'shared'>('personal')

const availableHashes = computed(() => {
  void nsRef.value
  return ns.entries().map((e) => e.hash)
})

function setAlias() {
  if (!aliasName.value || !aliasHash.value) return
  try {
    const c = cell(aliasCellId.value)
    if (aliasKind.value === 'personal') c.aliasLocal(aliasName.value, aliasHash.value)
    else c.aliasShared(aliasName.value, aliasHash.value)
    aliasName.value = ''
    aliasHash.value = ''
    bump()
  } catch (e) {
    alert((e as Error).message)
  }
}

/* live resolver */
const resolveCell = ref('alice')
const resolveName = ref('me')
const resolveResult = computed(() => {
  void nsRef.value
  const c = cell(resolveCell.value)
  const hash = c.resolve(resolveName.value)
  const entry = hash ? ns.get(hash) : undefined
  return { hash, entry }
})

/* state inspection */
const sharedList = computed(() => {
  void nsRef.value
  return ns.sharedAliases()
})

function personalFor(id: string) {
  void nsRef.value
  return ns.personalAliasesFor(id)
}

const allEntries = computed(() => {
  void nsRef.value
  return ns.entries()
})
</script>

<template>
  <div class="container">
    <h1>Local Namescope — two-detached-list pattern</h1>
    <p class="subtitle">
      LEFT (cells) one-way ➜ RIGHT (namescope: type catalog + aliases). Personal aliases
      isolated per cell; shared aliases visible to all. Personal wins over shared for
      same name in the cell that owns it. See <code>src/namescope.ts</code>.
    </p>

    <div class="layout">
      <!-- LEFT: cells -->
      <section class="panel panel-left">
        <h2>Cells <span class="count">{{ cellIds.length }}</span></h2>
        <p class="note">detached consumers — no cross-cell visibility of personal aliases</p>

        <div class="row">
          <input v-model="newCellId" placeholder="new cellId (e.g. carol)" @keyup.enter="addCell" />
          <button @click="addCell">+ cell</button>
        </div>

        <div v-for="id in cellIds" :key="id" class="cell-card">
          <div class="cell-head">
            <strong>{{ id }}</strong>
            <button class="small danger" @click="removeCell(id)">remove</button>
          </div>
          <div class="aliases-block">
            <div class="aliases-label">personal aliases:</div>
            <div v-if="personalFor(id).length === 0" class="empty">none</div>
            <div v-for="[name, hash] in personalFor(id)" :key="name" class="alias-row">
              <span class="alias-name">{{ name }}</span>
              <span class="arrow">→</span>
              <span class="alias-hash">{{ hash }}</span>
            </div>
          </div>
        </div>
      </section>

      <!-- RIGHT: namescope -->
      <section class="panel panel-right">
        <h2>Namescope <span class="count">{{ allEntries.length }} types</span></h2>
        <p class="note">virtual type catalog + shared alias registry</p>

        <details>
          <summary>Virtual type catalog ({{ allEntries.length }})</summary>
          <div class="catalog">
            <div v-for="e in allEntries" :key="e.hash" class="type-row">
              <code class="type-hash">{{ e.hash }}</code>
              <span class="type-tag">{{ e.type }}</span>
              <code class="type-payload">{{ JSON.stringify(e.payload) }}</code>
              <button class="small danger" @click="removeType(e.hash)">×</button>
            </div>
            <div class="add-type">
              <input v-model="newHash" placeholder="hash" />
              <input v-model="newType" placeholder="type" />
              <input v-model="newPayload" placeholder="payload JSON" />
              <button @click="addType">+</button>
            </div>
          </div>
        </details>

        <details open>
          <summary>Shared aliases ({{ sharedList.length }})</summary>
          <div v-if="sharedList.length === 0" class="empty">none</div>
          <div v-for="[name, hash] in sharedList" :key="name" class="alias-row">
            <span class="alias-name shared-tag">{{ name }}</span>
            <span class="arrow">→</span>
            <span class="alias-hash">{{ hash }}</span>
          </div>
        </details>

        <details open>
          <summary>Set alias</summary>
          <div class="alias-editor">
            <select v-model="aliasCellId">
              <option v-for="id in cellIds" :key="id">{{ id }}</option>
            </select>
            <select v-model="aliasKind">
              <option value="personal">personal</option>
              <option value="shared">shared</option>
            </select>
            <input v-model="aliasName" placeholder="alias name" />
            <select v-model="aliasHash">
              <option disabled value="">choose hash</option>
              <option v-for="h in availableHashes" :key="h" :value="h">{{ h }}</option>
            </select>
            <button @click="setAlias">set</button>
          </div>
        </details>
      </section>
    </div>

    <!-- Resolver -->
    <section class="resolver">
      <h2>Live resolver</h2>
      <p class="note">
        Try <code>me</code> in cells alice/bob → each resolves to their own msg.
        Try <code>thumb</code> (shared) → any cell resolves to the reaction.
      </p>
      <div class="row">
        <label>cell: <select v-model="resolveCell">
          <option v-for="id in cellIds" :key="id">{{ id }}</option>
        </select></label>
        <label>name: <input v-model="resolveName" /></label>
      </div>
      <div class="resolver-result">
        <div><strong>hash:</strong> <code>{{ resolveResult.hash ?? '(not resolved)' }}</code></div>
        <div v-if="resolveResult.entry">
          <strong>entry:</strong>
          <code>{{ JSON.stringify(resolveResult.entry) }}</code>
        </div>
      </div>
    </section>
  </div>
</template>

<style scoped>
.layout {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
  margin: 16px 0;
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
  gap: 8px;
}
.panel .count {
  color: #6e6a86;
  font-size: 12px;
  font-weight: normal;
}
.panel .note {
  color: #6e6a86;
  font-size: 12px;
  margin: 0 0 10px 0;
}
.panel-left {
  border-left: 3px solid #9ccfd8;
}
.panel-right {
  border-left: 3px solid #c4a7e7;
}

.row {
  display: flex;
  gap: 6px;
  margin-bottom: 10px;
}
input, select {
  background: #0f0f14;
  color: #e0def4;
  border: 1px solid #403d52;
  padding: 5px 8px;
  border-radius: 3px;
  font-size: 12px;
  font-family: ui-monospace, monospace;
}
button {
  background: #403d52;
  color: #e0def4;
  border: 1px solid #6e6a86;
  padding: 4px 10px;
  border-radius: 3px;
  cursor: pointer;
  font-size: 12px;
}
button:hover {
  background: #524f67;
}
button.small {
  padding: 2px 6px;
  font-size: 11px;
}
button.danger:hover {
  background: #eb6f92;
}

.cell-card {
  background: #0f0f14;
  border: 1px solid #2a2a33;
  border-radius: 4px;
  padding: 10px;
  margin-bottom: 8px;
}
.cell-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}
.cell-head strong {
  color: #9ccfd8;
  font-family: ui-monospace, monospace;
}
.aliases-block {
  border-top: 1px solid #2a2a33;
  padding-top: 6px;
}
.aliases-label {
  color: #6e6a86;
  font-size: 11px;
  margin-bottom: 4px;
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
  color: #f6c177;
  min-width: 80px;
}
.alias-name.shared-tag {
  color: #8ec07c;
}
.arrow {
  color: #6e6a86;
}
.alias-hash {
  color: #ebbcba;
  word-break: break-all;
}

details {
  margin-bottom: 10px;
}
summary {
  cursor: pointer;
  color: #c4a7e7;
  font-size: 13px;
  padding: 4px 0;
}

.catalog {
  padding: 6px 0;
}
.type-row {
  display: grid;
  grid-template-columns: 1fr 80px 1fr auto;
  gap: 8px;
  padding: 3px 0;
  font-size: 11px;
  align-items: center;
}
.type-hash { color: #9ccfd8; }
.type-tag { color: #c4a7e7; }
.type-payload { color: #e0def4; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.add-type {
  display: grid;
  grid-template-columns: 1fr 80px 1fr auto;
  gap: 6px;
  margin-top: 6px;
  padding-top: 6px;
  border-top: 1px solid #2a2a33;
}

.alias-editor {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  padding: 6px 0;
}

.empty {
  color: #6e6a86;
  font-size: 11px;
  padding: 4px 0;
}

.resolver {
  background: #1a1a1f;
  border: 1px solid #403d52;
  border-radius: 6px;
  padding: 14px;
  margin-top: 16px;
}
.resolver h2 {
  color: #c4a7e7;
  margin: 0 0 4px 0;
  font-size: 16px;
}
.resolver-result {
  background: #0f0f14;
  padding: 10px;
  border-radius: 4px;
  margin-top: 10px;
  font-size: 12px;
}
.resolver-result code {
  color: #f6c177;
}

code {
  background: transparent;
  font-family: ui-monospace, monospace;
  color: #f6c177;
}
</style>
