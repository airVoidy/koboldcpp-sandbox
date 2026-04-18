<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import {
  createEditor,
  $getRoot,
  $createParagraphNode,
  $createTextNode,
} from 'lexical'
import { registerRichText } from '@lexical/rich-text'
import { createEmptyHistoryState, registerHistory } from '@lexical/history'

const props = defineProps<{
  content?: string
  placeholder?: string
}>()

const target = ref<HTMLDivElement | null>(null)
let editor: ReturnType<typeof createEditor> | null = null
let cleanup: Array<() => void> = []

onMounted(() => {
  if (!target.value) return
  editor = createEditor({
    namespace: 'ContainerLexical-' + Math.random().toString(36).slice(2, 8),
    onError(err) {
      throw err
    },
    editable: true,
  })
  editor.setRootElement(target.value)
  cleanup.push(registerRichText(editor))
  cleanup.push(registerHistory(editor, createEmptyHistoryState(), 300))
  applyContent(props.content)
})

watch(
  () => props.content,
  (next) => applyContent(next),
)

function applyContent(content: string | undefined) {
  if (!editor || content == null) return
  editor.update(() => {
    const root = $getRoot()
    root.clear()
    for (const line of content.split('\n')) {
      const p = $createParagraphNode()
      p.append($createTextNode(line))
      root.append(p)
    }
  })
}

onBeforeUnmount(() => {
  cleanup.forEach((fn) => fn())
  cleanup = []
  editor?.setRootElement(null)
  editor = null
})
</script>

<template>
  <div class="lexical-container">
    <div ref="target" class="lexical-editable" :aria-placeholder="placeholder ?? 'Type here…'" />
  </div>
</template>

<style scoped>
.lexical-container {
  width: 100%;
  height: 100%;
  padding: 10px;
  box-sizing: border-box;
  background: #1a1a1f;
  overflow: auto;
}
.lexical-editable {
  outline: none;
  min-height: 100%;
  color: #e0def4;
  font-family: system-ui, -apple-system, sans-serif;
  font-size: 14px;
  line-height: 1.5;
}
</style>
