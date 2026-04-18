<script setup lang="ts">
import { shallowRef } from 'vue'
import type { LexicalEditor } from 'lexical'
import EditorHost from '../components/EditorHost.vue'
import AtomDemo from '../components/AtomDemo.vue'
import VirtualObjectDemo from '../components/VirtualObjectDemo.vue'

const editor = shallowRef<LexicalEditor | null>(null)

function onEditorReady(instance: LexicalEditor) {
  editor.value = instance
}
</script>

<template>
  <div class="container">
    <h1>Atom + Lexical Demo</h1>
    <p class="subtitle">
      Universal Atom + AtomRegistry + wrapper middleware over a Lexical rich-text editor.
      See <code>src/atom.ts</code>, <code>src/components/AtomDemo.vue</code>,
      <code>vite.config.ts</code>.
    </p>

    <EditorHost @ready="onEditorReady" />
    <AtomDemo :editor="editor" />
    <VirtualObjectDemo />
  </div>
</template>

<style scoped>
code {
  background: #0f0f14;
  padding: 2px 6px;
  border-radius: 3px;
  color: #f6c177;
  font-size: 12px;
}
</style>
