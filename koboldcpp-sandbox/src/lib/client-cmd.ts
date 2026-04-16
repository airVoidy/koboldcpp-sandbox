/**
 * Client-side CMD resolver.
 *
 * Navigation locally, everything else through server exec.
 * No optimistic state manipulation — server = source of truth.
 */
import type { ChatState, CmdResult } from '@/types/chat'
import * as api from './api'

export type StateUpdater = (fn: (prev: ChatState) => ChatState) => void

/** Parse CMD string into op + args */
function parse(cmd: string): { op: string; args: string[] } {
  const parts = cmd.replace(/^\//, '').split(/\s+/)
  return { op: parts[0]?.toLowerCase() ?? '', args: parts.slice(1) }
}

/** Read-only commands that don't need state refresh */
const READ_OPS = new Set(['dir', 'ls', 'cat', 'list', 'query'])

/**
 * Execute a CMD — navigation locally, everything else through server exec.
 */
export async function execCmd(
  cmd: string,
  user: string,
  state: ChatState,
  setState: StateUpdater,
): Promise<{ result: CmdResult; local: boolean }> {
  const { op, args } = parse(cmd)

  // ── Client-only: channel selection (pure navigation) ──
  if ((op === 'select' || op === 'cselect') && args[0]) {
    const name = args[0]
    setState(prev => ({ ...prev, active_channel: name }))
    // Fetch fresh state for that channel
    try {
      const fresh = await api.getState(name, user)
      setState(() => fresh)
    } catch {
      // server failed, navigation state still valid
    }
    return { result: { ok: true, selected: name }, local: true }
  }

  // ── Everything else: server exec ──
  try {
    const result = await api.exec(cmd, user)
    // Refresh state after mutations
    if (!READ_OPS.has(op)) {
      try {
        const fresh = await api.getState(state.active_channel ?? undefined, user)
        setState(() => fresh)
      } catch {
        // refresh failed
      }
    }
    return { result, local: false }
  } catch (e) {
    return { result: { error: String(e) }, local: false }
  }
}
