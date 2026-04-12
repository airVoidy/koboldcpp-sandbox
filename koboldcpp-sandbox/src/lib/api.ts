/**
 * API client for sandbox server.
 *
 * Only three endpoints matter:
 * - exec: send CMD → server dispatches → result
 * - batch: send multiple CMDs in one request
 * - getState: fetch current chat state (view projection)
 *
 * Everything else goes through exec as CMD strings.
 * Same pattern as vanilla pipeline-chat shellExec.
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

/** Execute a CMD in a scope */
export function exec(cmd: string, user: string, scope = 'CMD'): Promise<CmdResult> {
  return post('/pchat/exec', { cmd, user, scope, log: true })
}

/** Execute CMD batch */
export function batch(cmds: string[], user: string, scope = 'CMD'): Promise<CmdResult> {
  return post('/pchat/batch', { cmds, user, scope })
}

/** Get chat state (channels + messages view projection) */
export function getState(channel?: string, user = 'anon', since?: number): Promise<ChatState> {
  const params: Record<string, unknown> = { channel, user, msg_limit: 100 }
  if (since !== undefined) params.since = since
  return post('/pchat/view', params)
}
