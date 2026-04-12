/**
 * Client-side CMD resolver.
 *
 * Pure navigation ops execute locally (no server needed).
 * Everything else goes to server via exec.
 * No optimistic state manipulation — server is source of truth.
 *
 * Pattern: same as vanilla pipeline-chat shellExec.
 */
import type { ChatState, CmdResult } from '@/types/chat'
import * as api from './api'

export type StateUpdater = (fn: (prev: ChatState) => ChatState) => void

/** Commands that are pure client navigation — no server needed */
const CLIENT_OPS = new Set(['select', 'cselect', 'nav', 'cd'])

/** Parse CMD string into op + args */
function parse(cmd: string): { op: string; args: string[] } {
  const parts = cmd.replace(/^\//, '').split(/\s+/)
  return { op: parts[0]?.toLowerCase() ?? '', args: parts.slice(1) }
}

/**
 * Execute a CMD — navigation locally, everything else through server exec.
 * No optimistic updates. Server response = truth.
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
    // Update active_channel locally
    setState(prev => ({ ...prev, active_channel: name }))
    // Tell server + fetch fresh state for that channel
    try {
      const fresh = await api.getState(name, user)
      setState(() => fresh)
    } catch {
      // Server failed, client state still valid for navigation
    }
    return { result: { ok: true, selected: name }, local: true }
  }

  // ── Everything else: server exec → refresh state ──
  try {
    const result = await api.exec(cmd, user)
    // Refresh state after any mutation
    if (!isReadOnly(op)) {
      try {
        const fresh = await api.getState(state.active_channel ?? undefined, user)
        setState(() => fresh)
      } catch {
        // Refresh failed, stale state
      }
    }
    return { result, local: false }
  } catch (e) {
    return { result: { error: String(e) }, local: false }
  }
}

/** Read-only commands that don't need state refresh */
function isReadOnly(op: string): boolean {
  return ['dir', 'ls', 'cat', 'list', 'query', 'wiki'].includes(op)
}
