/**
 * API client — two endpoints, both exec-based.
 *
 * - /pchat/exec: single command
 * - /pchat/batch: batch of commands (already supports parallel-capable execution server-side)
 *
 * No /pchat/view, no /container/materialize. Everything flows through exec.
 * Panels subscribe to runtime objects in the Store; mutations via exec yield
 * results that get ingested, signals bump, panels re-render.
 */
import type { CmdResult, ChatState, ChatItem } from '@/types/chat'

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

/** Execute a single CMD. */
export function exec(cmd: string, user: string, scope = 'CMD'): Promise<CmdResult> {
  return post('/pchat/exec', { cmd, user, scope, log: true })
}

/** Execute a batch of CMDs server-side. Server handles parallel-safe ordering. */
export function batch(cmds: string[], user: string, scope = 'CMD'): Promise<CmdResult> {
  return post('/pchat/batch', { cmds, user, scope })
}

// ── Batch lambda wrapper ──

/**
 * ExecLambda — described intent, potentially dependent on prior lambdas.
 *
 * Flow (client-side):
 * 1. Split lambdas into independent (no dependsOn) vs dependent.
 * 2. Independent: send as /pchat/batch (one HTTP, parallel-safe on server).
 * 3. Dependent: after deps resolved, substitute @name refs in cmd, send sequentially.
 *
 * This matches the described design: first expand batch as a whole, resolve lambdas
 * to promises/schema, then fill in relative values. Avoids linear step-by-step.
 */
export interface ExecLambda {
  cmd: string
  /** Optional binding name — lets later lambdas reference this result via @name. */
  name?: string
  /** Names of prior lambdas this one depends on (their results substitute @name in cmd). */
  dependsOn?: string[]
}

export async function batchLambda(
  lambdas: ExecLambda[],
  user: string,
): Promise<Record<string, CmdResult>> {
  const results: Record<string, CmdResult> = {}

  // Phase 1: resolve independent lambdas in parallel via /pchat/batch
  const independent = lambdas.filter((l) => !l.dependsOn?.length)
  const dependent = lambdas.filter((l) => l.dependsOn?.length)

  if (independent.length > 0) {
    const cmds = independent.map((l) => l.cmd)
    const batchRes = (await batch(cmds, user)) as { results?: CmdResult[] }
    const batchResults = batchRes.results ?? []
    independent.forEach((l, i) => {
      if (l.name) results[l.name] = batchResults[i] ?? {}
    })
  }

  // Phase 2: dependent lambdas — substitute @name, send sequentially
  // (future: could topologically sort and batch independent groups)
  for (const l of dependent) {
    const substituted = substituteRefs(l.cmd, results)
    const r = await exec(substituted, user)
    if (l.name) results[l.name] = r
  }

  return results
}

/** Substitute @name tokens in cmd string with prior lambda results (JSON-stringified). */
function substituteRefs(cmd: string, results: Record<string, CmdResult>): string {
  return cmd.replace(/@([a-zA-Z_][a-zA-Z0-9_]*)/g, (_, name) => {
    const value = results[name]
    if (value === undefined) return `@${name}`
    return typeof value === 'string' ? value : JSON.stringify(value)
  })
}

// ── State loading via exec /query (replaces old /pchat/view) ──

/**
 * Tree node shape returned by /query command.
 */
interface QueryNode {
  path?: string
  name?: string
  meta?: Record<string, unknown>
  data?: Record<string, unknown>
  children?: QueryNode[]
}

/**
 * Load chat state via exec /query commands.
 * Batches the channel list + active channel messages in one /pchat/batch round-trip.
 */
export async function loadState(
  channel: string | null | undefined,
  user: string,
): Promise<ChatState> {
  const cmds = ['/query pchat/channels --depth=2 --limit=100']
  if (channel) cmds.push(`/query pchat/channels/${channel} --depth=2 --limit=50`)

  const res = (await batch(cmds, user)) as { results?: QueryNode[] }
  const results = res.results ?? []
  const channelsRes = results[0]
  const messagesRes = channel ? results[1] : null

  return treeToChatState(channelsRes, messagesRes, channel ?? null, user)
}

function treeToChatState(
  channelsRes: QueryNode | undefined,
  messagesRes: QueryNode | null,
  active: string | null,
  user: string,
): ChatState {
  const channels: ChatItem[] = (channelsRes?.children ?? [])
    .filter((c) => (c.meta as Record<string, unknown> | undefined)?.type === 'channel')
    .map(toChatItem)

  const messages: ChatItem[] = messagesRes
    ? (messagesRes.children ?? [])
        .filter((m) => (m.meta as Record<string, unknown> | undefined)?.type === 'message')
        .map(toChatItem)
    : []

  return {
    channels,
    messages,
    active_channel: active,
    user,
    ts: new Date().toISOString(),
  }
}

function toChatItem(n: QueryNode): ChatItem {
  return {
    name: n.name ?? '',
    path: n.path ?? '',
    meta: (n.meta as ChatItem['meta']) ?? { type: 'card' },
    data: (n.data as ChatItem['data']) ?? {},
  }
}
