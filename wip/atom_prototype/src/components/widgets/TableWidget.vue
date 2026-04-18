<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  rows?: Array<Record<string, unknown>>
  columns?: string[]
}>()

const rows = computed(() => props.rows ?? [])
const cols = computed(() => {
  if (props.columns && props.columns.length) return props.columns
  const set = new Set<string>()
  for (const r of rows.value) for (const k of Object.keys(r)) set.add(k)
  return [...set]
})
</script>

<template>
  <div class="table-widget">
    <table v-if="rows.length">
      <thead>
        <tr>
          <th v-for="c in cols" :key="c">{{ c }}</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="(r, i) in rows" :key="i">
          <td v-for="c in cols" :key="c">{{ r[c] }}</td>
        </tr>
      </tbody>
    </table>
    <div v-else class="empty">(no rows)</div>
    <div class="meta">{{ rows.length }} row(s) · {{ cols.length }} col(s)</div>
  </div>
</template>

<style scoped>
.table-widget {
  height: 100%;
  display: flex;
  flex-direction: column;
  padding: 8px;
  font-size: 11px;
  font-family: ui-monospace, monospace;
  box-sizing: border-box;
}
table {
  flex: 1;
  border-collapse: collapse;
  width: 100%;
  overflow: auto;
}
th {
  background: #2a2a33;
  color: #c4a7e7;
  text-align: left;
  padding: 3px 6px;
  border-bottom: 1px solid #403d52;
  position: sticky;
  top: 0;
}
td {
  padding: 2px 6px;
  border-bottom: 1px solid #2a2a33;
  color: #e0def4;
}
.empty {
  flex: 1;
  display: grid;
  place-items: center;
  color: #6e6a86;
}
.meta {
  color: #6e6a86;
  font-size: 10px;
  padding-top: 4px;
  border-top: 1px solid #2a2a33;
}
</style>
