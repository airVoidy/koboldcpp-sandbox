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

/**
 * Full Lexical rich-text editor, usable as a real text editor inside a
 * floating container cell.
 *
 * Props:
 *   content     — initial content (only applied on mount; subsequent prop
 *                 changes DO NOT overwrite user edits unless the prop
 *                 actually changes to a different value).
 *   placeholder — visible when the editor is empty.
 *
 * Emits:
 *   content-change — string, fired whenever user edits (on each update tick).
 */

const props = defineProps<{
  content?: string
  placeholder?: string
}>()

const emit = defineEmits<{
  (e: 'content-change', text: string): void
}>()

const target = ref<HTMLDivElement | null>(null)
let editor: ReturnType<typeof createEditor> | null = null
let cleanup: Array<() => void> = []
let lastAppliedContent: string | undefined = undefined

onMounted(() => {
  if (!target.value) return
  editor = createEditor({
    namespace: 'ContainerLexical-' + Math.random().toString(36).slice(2, 8),
    onError(err) {
      // Surface instead of crashing the view.
      // eslint-disable-next-line no-console
      console.error('[LexicalContainer] editor error:', err)
    },
    editable: true,
  })
  editor.setRootElement(target.value)
  cleanup.push(registerRichText(editor))
  cleanup.push(registerHistory(editor, createEmptyHistoryState(), 300))

  // Emit content on each update.
  cleanup.push(
    editor.registerUpdateListener(({ editorState }) => {
      editorState.read(() => {
        const text = $getRoot().getTextContent()
        emit('content-change', text)
      })
    }),
  )

  if (props.content != null) {
    applyContent(props.content)
    lastAppliedContent = props.content
  }
})

// Only reapply content if the prop literally changed to a new value
// (prevents wiping user edits on parent re-render).
watch(
  () => props.content,
  (next) => {
    if (next == null) return
    if (next === lastAppliedContent) return
    applyContent(next)
    lastAppliedContent = next
  },
)

function applyContent(content: string) {
  if (!editor) return
  editor.update(() => {
    const root = $getRoot()
    root.clear()
    for (const line of content.split('\n')) {
      const p = $createParagraphNode()
      if (line.length > 0) p.append($createTextNode(line))
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
    <div
      ref="target"
      class="lexical-editable"
      contenteditable="true"
      spellcheck="true"
      role="textbox"
      aria-multiline="true"
      :data-placeholder="placeholder ?? 'Type here…'"
    />
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
  position: relative;
}

.lexical-editable {
  outline: none;
  min-height: 100%;
  color: #e0def4;
  font-family: system-ui, -apple-system, sans-serif;
  font-size: 14px;
  line-height: 1.5;
  caret-color: #c4a7e7;
  cursor: text;
  white-space: pre-wrap;
  word-wrap: break-word;
  position: relative;
}

/* Lexical adds :empty when the editor truly has no content; paragraphs
   still show as empty <p>. Use :has() check for an all-empty state. */
.lexical-editable:empty::before,
.lexical-editable > p:only-child:empty::before {
  content: attr(data-placeholder);
  color: #6e6a86;
  pointer-events: none;
  position: absolute;
  top: 0;
}

.lexical-editable:focus-visible {
  outline: 1px solid rgba(196, 167, 231, 0.35);
  outline-offset: 2px;
}
</style>
