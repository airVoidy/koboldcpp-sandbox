/**
 * API client — one exec endpoint, one view for bootstrap.
 * Same as vanilla pipeline-chat shellExec pattern.
 */
import type { CmdResult, ChatState } from '@/types/chat'

const BASE = '/api'

async function post<T = unknown>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
  return res.json()
}

/** Execute a CMD — the only mutation endpoint */
export function exec(cmd: string, user: string, scope = 'CMD'): Promise<CmdResult> {
  return post('/pchat/exec', { cmd, user, scope, log: true })
}

/** Execute CMD batch */
export function batch(cmds: string[], user: string, scope = 'CMD'): Promise<CmdResult> {
  return post('/pchat/batch', { cmds, user, scope })
}

/** Bootstrap: get current chat state (legacy view, will move to exec) */
export function getState(channel?: string, user = 'anon'): Promise<ChatState> {
  return post('/pchat/view', { channel, user, msg_limit: 100 })
}
