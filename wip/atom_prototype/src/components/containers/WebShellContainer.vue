<script setup lang="ts">
/**
 * Interactive mini-shell with a virtual filesystem. Real, usable — but
 * intentionally small-scope (no @webcontainer/api, no actual Node). Covers:
 *   echo, date, pwd, ls, cat, touch, rm, mkdir, cd, help, clear, history.
 *
 * Enough to feel like a shell for exploring the interaction pattern.
 * Upgrades (real web-container, just-bash + xterm) can slot in under the
 * same component surface later.
 */

import { nextTick, onMounted, ref } from 'vue'

const props = defineProps<{
  /** Initial command to execute once the shell mounts. */
  cmd?: string
  /** Pre-seeded files in the virtual FS, keyed by absolute path. */
  files?: Record<string, string>
}>()

type VEntry = { kind: 'file'; content: string } | { kind: 'dir' }

// Absolute path → entry. Keys always start with '/'.
const fs = ref<Record<string, VEntry>>({
  '/': { kind: 'dir' },
  '/home': { kind: 'dir' },
  '/home/user': { kind: 'dir' },
  '/home/user/README.md': {
    kind: 'file',
    content: '# virtual FS\n\ntry: ls, cat README.md, help\n',
  },
  ...Object.fromEntries(
    Object.entries(props.files ?? {}).map(([k, v]) => [k, { kind: 'file', content: v } as VEntry]),
  ),
})

const cwd = ref('/home/user')
const input = ref('')
const history = ref<string[]>([])
const historyCursor = ref<number | null>(null)
const lines = ref<Array<{ kind: 'cmd' | 'out' | 'err' | 'info'; text: string }>>([
  { kind: 'info', text: 'mini-shell — type `help` for commands' },
])
const outputRoot = ref<HTMLDivElement | null>(null)

function resolvePath(raw: string): string {
  let p = raw.trim()
  if (p === '') return cwd.value
  if (!p.startsWith('/')) p = (cwd.value === '/' ? '' : cwd.value) + '/' + p
  const parts: string[] = []
  for (const seg of p.split('/')) {
    if (seg === '' || seg === '.') continue
    if (seg === '..') parts.pop()
    else parts.push(seg)
  }
  return '/' + parts.join('/')
}

function parentOf(path: string): string {
  if (path === '/') return '/'
  const i = path.lastIndexOf('/')
  return i <= 0 ? '/' : path.slice(0, i)
}

function baseOf(path: string): string {
  if (path === '/') return ''
  const i = path.lastIndexOf('/')
  return path.slice(i + 1)
}

async function scrollToBottom() {
  await nextTick()
  if (outputRoot.value) {
    outputRoot.value.scrollTop = outputRoot.value.scrollHeight
  }
}

function appendLine(kind: 'cmd' | 'out' | 'err' | 'info', text: string) {
  lines.value.push({ kind, text })
  void scrollToBottom()
}

function run(cmdLine: string) {
  const trimmed = cmdLine.trim()
  if (!trimmed) return

  appendLine('cmd', `${cwd.value} $ ${trimmed}`)
  history.value.push(trimmed)
  historyCursor.value = null

  const [cmd, ...args] = trimmed.split(/\s+/)
  try {
    switch (cmd) {
      case 'help':
        appendLine(
          'out',
          'commands: echo, date, pwd, ls [path], cat <file>, touch <file>, rm <path>, mkdir <dir>, cd <dir>, history, clear, help',
        )
        break
      case 'echo':
        appendLine('out', args.join(' '))
        break
      case 'date':
        appendLine('out', new Date().toISOString())
        break
      case 'pwd':
        appendLine('out', cwd.value)
        break
      case 'ls': {
        const target = args[0] ? resolvePath(args[0]) : cwd.value
        if (fs.value[target]?.kind !== 'dir') throw new Error(`not a directory: ${target}`)
        const prefix = target === '/' ? '/' : target + '/'
        const entries = Object.keys(fs.value)
          .filter(
            (p) =>
              p !== target &&
              p.startsWith(prefix) &&
              !p.slice(prefix.length).includes('/'),
          )
          .sort()
        if (entries.length === 0) appendLine('out', '')
        else {
          appendLine(
            'out',
            entries
              .map((p) => {
                const name = baseOf(p)
                return fs.value[p]?.kind === 'dir' ? `${name}/` : name
              })
              .join('  '),
          )
        }
        break
      }
      case 'cat': {
        if (!args[0]) throw new Error('cat: missing operand')
        const path = resolvePath(args[0])
        const entry = fs.value[path]
        if (!entry) throw new Error(`cat: ${args[0]}: no such file`)
        if (entry.kind !== 'file') throw new Error(`cat: ${args[0]}: is a directory`)
        appendLine('out', entry.content)
        break
      }
      case 'touch': {
        if (!args[0]) throw new Error('touch: missing operand')
        const path = resolvePath(args[0])
        if (!fs.value[parentOf(path)] || fs.value[parentOf(path)].kind !== 'dir') {
          throw new Error(`touch: parent dir missing: ${parentOf(path)}`)
        }
        if (!fs.value[path]) fs.value[path] = { kind: 'file', content: '' }
        break
      }
      case 'mkdir': {
        if (!args[0]) throw new Error('mkdir: missing operand')
        const path = resolvePath(args[0])
        if (fs.value[path]) throw new Error(`mkdir: ${args[0]}: exists`)
        if (!fs.value[parentOf(path)] || fs.value[parentOf(path)].kind !== 'dir') {
          throw new Error(`mkdir: parent dir missing`)
        }
        fs.value[path] = { kind: 'dir' }
        break
      }
      case 'rm': {
        if (!args[0]) throw new Error('rm: missing operand')
        const path = resolvePath(args[0])
        if (!fs.value[path]) throw new Error(`rm: ${args[0]}: no such file`)
        if (fs.value[path].kind === 'dir') {
          // Also remove descendants.
          const prefix = path + '/'
          for (const k of Object.keys(fs.value)) {
            if (k === path || k.startsWith(prefix)) delete fs.value[k]
          }
        } else {
          delete fs.value[path]
        }
        break
      }
      case 'cd': {
        const target = resolvePath(args[0] ?? '/home/user')
        if (!fs.value[target] || fs.value[target].kind !== 'dir') {
          throw new Error(`cd: ${args[0]}: not a directory`)
        }
        cwd.value = target
        break
      }
      case 'history':
        appendLine('out', history.value.map((h, i) => `  ${i + 1}  ${h}`).join('\n'))
        break
      case 'clear':
        lines.value = []
        break
      default:
        throw new Error(`${cmd}: command not found`)
    }
  } catch (err) {
    appendLine('err', err instanceof Error ? err.message : String(err))
  }
}

function onSubmit() {
  const cmd = input.value
  input.value = ''
  run(cmd)
}

function onKey(event: KeyboardEvent) {
  if (event.key === 'ArrowUp') {
    event.preventDefault()
    if (history.value.length === 0) return
    const cursor = historyCursor.value === null ? history.value.length : historyCursor.value
    const next = Math.max(0, cursor - 1)
    historyCursor.value = next
    input.value = history.value[next] ?? ''
  } else if (event.key === 'ArrowDown') {
    event.preventDefault()
    if (historyCursor.value === null) return
    const next = historyCursor.value + 1
    if (next >= history.value.length) {
      historyCursor.value = null
      input.value = ''
    } else {
      historyCursor.value = next
      input.value = history.value[next]
    }
  }
}

onMounted(() => {
  if (props.cmd) run(props.cmd)
})
</script>

<template>
  <div class="shell">
    <div ref="outputRoot" class="output">
      <div
        v-for="(line, i) in lines"
        :key="i"
        class="line"
        :class="`line-${line.kind}`"
      >{{ line.text }}</div>
    </div>
    <form class="input-row" @submit.prevent="onSubmit">
      <span class="prompt">{{ cwd }} $</span>
      <input
        v-model="input"
        type="text"
        class="cmd-input"
        autocomplete="off"
        autocapitalize="off"
        spellcheck="false"
        @keydown="onKey"
      />
    </form>
  </div>
</template>

<style scoped>
.shell {
  height: 100%;
  box-sizing: border-box;
  background: #0f0f14;
  display: flex;
  flex-direction: column;
  font-family: ui-monospace, monospace;
  font-size: 12px;
}

.output {
  flex: 1;
  padding: 8px 10px;
  overflow-y: auto;
  white-space: pre-wrap;
}

.line {
  padding: 1px 0;
}

.line-cmd {
  color: #9ccfd8;
}

.line-out {
  color: #e0def4;
}

.line-err {
  color: #eb6f92;
}

.line-info {
  color: #6e6a86;
  font-style: italic;
}

.input-row {
  display: flex;
  gap: 6px;
  align-items: center;
  padding: 6px 10px;
  border-top: 1px solid #2a2a33;
  background: #1a1a1f;
}

.prompt {
  color: #f6c177;
  white-space: nowrap;
}

.cmd-input {
  flex: 1;
  background: transparent;
  color: #e0def4;
  border: none;
  font-family: inherit;
  font-size: 12px;
  outline: none;
}
</style>
