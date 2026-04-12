/**
 * Client-side CMD resolver.
 *
 * Pure state operations execute locally (optimistic).
 * Mutations dispatch to server, then reconcile.
 *
 * Pattern: client resolves what it can, server handles the rest.
 * Same CMD, two runtimes.
 */
import type { ChatState, ChatItem, CmdResult } from '@/types/chat'
import * as api from './api'

export type StateUpdater = (fn: (prev: ChatState) => ChatState) => void

/** Commands that are pure client state — no server needed */
const CLIENT_OPS = new Set(['select', 'cselect', 'nav', 'cd'])

/** Commands that are read-only — can use cache */
const READ_OPS = new Set(['dir', 'ls', 'cat', 'list', 'query', 'wiki status', 'wiki list'])

/** Parse CMD string into op + args */
function parse(cmd: string): { op: string; args: string[] } {
  const parts = cmd.replace(/^\//, '').split(/\s+/)
  return { op: parts[0]?.toLowerCase() ?? '', args: parts.slice(1) }
}

/**
 * Execute a CMD — client-first, server-fallback.
 * Returns result and whether server was called.
 */
export async function execCmd(
  cmd: string,
  user: string,
  state: ChatState,
  setState: StateUpdater,
): Promise<{ result: CmdResult; local: boolean }> {
  const { op, args } = parse(cmd)

  // ── Client-only: select channel ──
  if ((op === 'select' || op === 'cselect') && args[0]) {
    const name = args[0]
    const channel = state.channels.find(
      ch => (ch.meta?.name ?? ch.name) === name
    )
    if (channel) {
      // Optimistic: update active_channel immediately
      setState(prev => ({ ...prev, active_channel: name }))

      // Background: tell server + fetch messages for new channel
      api.selectChannel(name, user)
        .then(() => api.getState(name, user))
        .then(fresh => setState(() => fresh))
        .catch(() => {}) // server confirm failed, client state still valid

      return { result: { ok: true, selected: name }, local: true }
    }
  }

  // ── Server mutations with optimistic UI ──
  if (op === 'cpost' && args.length > 0) {
    const text = args.join(' ')
    const optimisticMsg: ChatItem = {
      name: `msg_pending_${Date.now()}`,
      path: '',
      meta: { type: 'message', user, ts: new Date().toISOString() },
      data: { content: text },
    }
    // Optimistic: add message immediately
    setState(prev => ({
      ...prev,
      messages: [...prev.messages, optimisticMsg],
    }))

    // Server: post + reconcile
    try {
      await api.postMessage(text, user)
      const fresh = await api.getState(state.active_channel ?? undefined, user)
      setState(() => fresh)
      return { result: { ok: true }, local: false }
    } catch (e) {
      // Rollback optimistic message
      setState(prev => ({
        ...prev,
        messages: prev.messages.filter(m => m.name !== optimisticMsg.name),
      }))
      return { result: { error: String(e) }, local: false }
    }
  }

  if (op === 'creact' && args.length >= 2) {
    const [msgId, emoji] = args
    // Optimistic: toggle reaction locally
    setState(prev => ({
      ...prev,
      messages: prev.messages.map(m => {
        if (m.name !== msgId) return m
        const reactions = { ...(m.data?.reactions ?? {}) }
        const entry = reactions[emoji] ?? { users: [], count: 0 }
        const users = entry.users.includes(user)
          ? entry.users.filter((u: string) => u !== user)
          : [...entry.users, user]
        if (users.length === 0) {
          delete reactions[emoji]
        } else {
          reactions[emoji] = { users, count: users.length }
        }
        return { ...m, data: { ...m.data, reactions } }
      }),
    }))

    // Server confirm in background
    api.react(msgId, emoji, user)
      .then(() => api.getState(state.active_channel ?? undefined, user))
      .then(fresh => setState(() => fresh))
      .catch(() => {})

    return { result: { ok: true }, local: true }
  }

  // ── Client-side JSONata eval ──
  if (op === 'mjsonata') {
    try {
      const { evaluate } = await import('./query')
      // Simple: evaluate expression against current state
      const expr = args.join(' ')
      const data = {
        messages: state.messages,
        channels: state.channels,
        active_channel: state.active_channel,
      }
      const result = await evaluate(expr, data)
      return { result: { ok: true, result, _local: true }, local: true }
    } catch (e) {
      // Fallback to server if client eval fails
    }
  }

  // ── Fallback: server exec ──
  const result = await api.exec(cmd, user)
  // Refresh state after mutation
  if (!READ_OPS.has(op)) {
    api.getState(state.active_channel ?? undefined, user)
      .then(fresh => setState(() => fresh))
      .catch(() => {})
  }
  return { result, local: false }
}
