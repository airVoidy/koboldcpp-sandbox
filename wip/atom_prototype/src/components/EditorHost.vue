<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import {
  createEditor,
  $getRoot,
  $createParagraphNode,
  $createTextNode,
  type LexicalEditor,
} from 'lexical'
import { registerRichText } from '@lexical/rich-text'
import { createEmptyHistoryState, registerHistory } from '@lexical/history'

const emit = defineEmits<{
  ready: [editor: LexicalEditor]
}>()

const mountTarget = ref<HTMLDivElement | null>(null)
let editor: LexicalEditor | null = null
let unregisterRichText: (() => void) | null = null
let unregisterHistory: (() => void) | null = null

onMounted(() => {
  if (!mountTarget.value) return

  editor = createEditor({
    namespace: 'AtomPrototype',
    onError(error) {
      // Prototype: surface errors loudly.
      throw error
    },
    editable: true,
  })

  editor.setRootElement(mountTarget.value)
  unregisterRichText = registerRichText(editor)
  unregisterHistory = registerHistory(editor, createEmptyHistoryState(), 300)

  // Seed initial content so the editor isn't empty on load.
  editor.update(() => {
    const root = $getRoot()
    if (root.getFirstChild() == null) {
      const p = $createParagraphNode()
      p.append($createTextNode('Type here or press the atom buttons below.'))
      root.append(p)
    }
  })

  emit('ready', editor)
})

onBeforeUnmount(() => {
  unregisterRichText?.()
  unregisterHistory?.()
  editor?.setRootElement(null)
  editor = null
})
</script>

<template>
  <div class="editor-host">
    <div ref="mountTarget" class="editor-input" contenteditable="true" aria-label="Lexical editor"></div>
  </div>
</template>
