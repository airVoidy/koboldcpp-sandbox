<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { LexicalEditor } from 'lexical'
import { $getRoot, $createParagraphNode, $createTextNode } from 'lexical'
import { AtomRegistry, type AtomRunResult, mkAtom, wrappers } from '../atom'

const props = defineProps<{
  editor: LexicalEditor | null
}>()

const log = ref<AtomRunResult[]>([])
const registry = new AtomRegistry()
registry.onRun((result) => {
  log.value = [result, ...log.value].slice(0, 30)
})

// Wrapper layer toggles — demonstrate decorators without changing atom identity.
const enabledLogging = ref(true)
const enabledTiming = ref(true)
const enabledCaching = ref(false)

watch(
  [enabledLogging, enabledTiming, enabledCaching],
  () => {
    // Re-build registry wrappers from current toggles.
    // Note: in a real runtime we'd unregister surgically; here we rebuild
    // the entire wrapper set when toggles change.
    ;(registry as unknown as { wrappers: unknown[] }).wrappers = []
    if (enabledLogging.value) registry.registerWrapper(wrappers.logging())
    if (enabledTiming.value) registry.registerWrapper(wrappers.timing())
    if (enabledCaching.value) registry.registerWrapper(wrappers.caching())
  },
  { immediate: true },
)

// Register atoms whenever the editor becomes available.
watch(
  () => props.editor,
  (editor) => {
    if (!editor) return

    registry.register(
      mkAtom(
        'insert-text',
        ['text-to-insert'],
        {
          type: 'lambda',
          fn: (input) => {
            const text = String(input)
            editor.update(() => {
              const root = $getRoot()
              const p = $createParagraphNode()
              p.append($createTextNode(text))
              root.append(p)
            })
            return { inserted: text }
          },
        },
        ['last-insert-result'],
        { kind: 'op', tags: ['editor', 'mutation'] },
      ),
    )

    registry.register(
      mkAtom(
        'clear-editor',
        [],
        {
          type: 'lambda',
          fn: () => {
            editor.update(() => {
              $getRoot().clear()
            })
            return { cleared: true }
          },
        },
        ['last-clear-result'],
        { kind: 'op', tags: ['editor', 'mutation'] },
      ),
    )

    registry.register(
      mkAtom(
        'len-projection',
        [],
        {
          type: 'lambda',
          fn: () => {
            let length = 0
            editor.getEditorState().read(() => {
              length = $getRoot().getTextContent().length
            })
            return { length }
          },
        },
        ['text-length'],
        { kind: 'projection', tags: ['editor', 'read-only'] },
      ),
    )

    // Pure-computation atom for showcasing caching. Deterministic input → output.
    registry.register(
      mkAtom(
        'slow-double',
        ['n'],
        {
          type: 'lambda',
          fn: async (input) => {
            // Simulate work; caching should eliminate repeats.
            await new Promise((r) => setTimeout(r, 60))
            return { doubled: Number(input) * 2 }
          },
        },
        ['double-result'],
        { kind: 'op', tags: ['pure', 'cacheable'] },
      ),
    )
  },
  { immediate: true },
)

const disabled = computed(() => props.editor == null)

function runInsert() {
  const samples = ['hello atom', '✨ atoms flowing', 'lexical + atom = ⚡', '42']
  const pick = samples[Math.floor(Math.random() * samples.length)]
  registry.setValue('text-to-insert', pick)
  void registry.run('insert-text')
}

function runDouble() {
  // Fixed input so cache wrapper can demonstrate hit/miss behavior.
  registry.setValue('n', 21)
  void registry.run('slow-double')
}
</script>

<template>
  <div class="demo">
    <label>
      <input type="checkbox" v-model="enabledLogging" />
      log wrapper
    </label>
    <label>
      <input type="checkbox" v-model="enabledTiming" />
      timing wrapper
    </label>
    <label>
      <input type="checkbox" v-model="enabledCaching" />
      caching wrapper
    </label>
  </div>

  <div class="demo">
    <button type="button" :disabled="disabled" @click="runInsert">Insert via Atom</button>
    <button type="button" :disabled="disabled" @click="() => registry.run('clear-editor')">Clear via Atom</button>
    <button type="button" :disabled="disabled" @click="() => registry.run('len-projection')">Project text length</button>
    <button type="button" :disabled="disabled" @click="runDouble">Slow-double (try with caching)</button>
  </div>

  <pre class="log">
    <span v-if="log.length === 0" style="color: #6e6a86">no atom runs yet — click a button</span>
    <div v-for="(entry, i) in log" :key="i" class="log-entry">
      <strong>{{ entry.atomId }}</strong> · {{ entry.durationMs.toFixed(2) }}ms
      {{ '\n  inputs: ' }}{{ JSON.stringify(entry.inputs) }}
      {{ '\n  output: ' }}{{ JSON.stringify(entry.output) }}
      <template v-if="entry.trace">
        {{ '\n  trace:' }}
        <template v-for="(t, j) in entry.trace" :key="j">
          {{ '\n    ' }}[{{ t.tAt.toFixed(2) }}ms] <em style="color: #c4a7e7">{{ t.wrapperId }}</em> · {{ t.event }}{{ t.note != null ? ' · ' + JSON.stringify(t.note) : '' }}
        </template>
      </template>
    </div>
  </pre>
</template>
