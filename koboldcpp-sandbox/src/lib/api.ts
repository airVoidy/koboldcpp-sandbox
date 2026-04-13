/** API client for sandbox server at localhost:5002 */
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

async function get<T = unknown>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`)
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

/** Get full chat state (channels + messages) */
export function getState(channel?: string, user = 'anon', since?: number): Promise<ChatState> {
  const params: Record<string, unknown> = { channel, user, msg_limit: 100 }
  if (since !== undefined) params.since = since
  return post('/pchat/view', params)
}

/** Convenience: select channel */
export function selectChannel(name: string, user: string) {
  return exec(`/cselect ${name}`, user)
}

/** Convenience: post message */
export function postMessage(text: string, user: string) {
  return exec(`/cpost ${text}`, user)
}

/** Convenience: create channel */
export function createChannel(name: string, user: string) {
  return exec(`/cmkchannel ${name}`, user)
}

/** Convenience: toggle reaction */
export function react(msgId: string, emoji: string, user: string) {
  return exec(`/creact ${msgId} ${emoji}`, user)
}

/** Template aggregation projection */
export function getProjection(template: string, scope?: string) {
  return post('/pchat/projection', { template, scope: scope ?? '' })
}

/** Single message projection */
export function getMessageProjection(path: string) {
  return post('/pchat/message-projection', { path })
}

/** Wiki commands */
export const wiki = {
  status: (user: string) => exec('/wiki status', user),
  list: (user: string) => exec('/wiki list', user),
  read: (slug: string, user: string) => exec(`/wiki read ${slug}`, user),
}
