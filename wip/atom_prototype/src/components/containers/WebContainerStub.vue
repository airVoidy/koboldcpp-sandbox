<script setup lang="ts">
/**
 * Stub for a web-container-style shell carrier. Real integration (see
 * wip/runtime_refs/web-container) adds just-bash / xterm / quickjs-emscripten
 * as a 3-worker split. Here we display what shape the atom output takes.
 */
const props = defineProps<{
  /** The bash command the atom ran. */
  cmd?: string
  /** Captured stdout. */
  stdout?: string
  /** Captured stderr. */
  stderr?: string
  /** Exit code. */
  exitCode?: number
}>()
</script>

<template>
  <div class="web-container-stub">
    <div class="cmdline">
      <span class="prompt">$</span>
      <span class="cmd">{{ props.cmd ?? '(no command)' }}</span>
    </div>
    <pre v-if="props.stdout" class="stdout">{{ props.stdout }}</pre>
    <pre v-if="props.stderr" class="stderr">{{ props.stderr }}</pre>
    <div class="exit" v-if="props.exitCode != null">exit: {{ props.exitCode }}</div>
  </div>
</template>

<style scoped>
.web-container-stub {
  padding: 10px;
  height: 100%;
  box-sizing: border-box;
  overflow: auto;
  background: #0f0f14;
  font-family: ui-monospace, monospace;
  font-size: 12px;
}
.cmdline {
  color: #9ccfd8;
  margin-bottom: 6px;
}
.prompt { color: #f6c177; margin-right: 6px; }
.cmd { color: #e0def4; }
pre {
  white-space: pre-wrap;
  margin: 0;
  padding: 4px 0;
}
.stdout { color: #e0def4; }
.stderr { color: #eb6f92; }
.exit {
  color: #6e6a86;
  margin-top: 8px;
  font-size: 11px;
}
</style>
