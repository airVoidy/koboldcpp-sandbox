import { useCallback, useEffect, useMemo, useState } from 'react'
import { useLocalStorageState } from 'ahooks'
import * as api from '@/lib/api'
import { useSandbox } from '@/hooks/useSandbox'
import type { ChatItem, ChatState, CmdResult, NodeData, NodeMeta } from '@/types/chat'

const LS_USER = 'pchat_user'
const LS_CHANNEL = 'pchat_active_channel'

function byPathDepth(a: ChatItem, b: ChatItem): number {
  return a.path.localeCompare(b.path, undefined, { numeric: true })
}

function lastSegment(path: string): string {
  const parts = path.split('/')
  return parts[parts.length - 1] ?? path
}

function toNodeMeta(meta: Record<string, unknown>, fallbackType: string): NodeMeta {
  return {
    type: typeof meta.type === 'string' ? meta.type : fallbackType,
    user: typeof meta.user === 'string' ? meta.user : undefined,
    ts: typeof meta.ts === 'string' ? meta.ts : undefined,
    name: typeof meta.name === 'string' ? meta.name : undefined,
  }
}

function toNodeData(data: Record<string, unknown>): NodeData {
  return data as NodeData
}

function isReadOnlyOp(op: string): boolean {
  return new Set([
    'dir', 'ls', 'cat', 'list', 'query', 'mjsonata', 'mproject', 'mcheckpoint', 'wiki',
  ]).has(op)
}

function parseCmd(cmd: string): { op: string; args: string[] } {
  const parts = cmd.trim().replace(/^\//, '').split(/\s+/).filter(Boolean)
  return { op: (parts[0] ?? '').toLowerCase(), args: parts.slice(1) }
}

export function useChat() {
  const {
    sandbox,
    serverState,
    loadServerState,
    serverExec,
    setUser: setSandboxUser,
  } = useSandbox()

  const [user, setUser] = useLocalStorageState<string>(LS_USER, { defaultValue: 'anon' })
  const [activeChannel, setActiveChannel] = useLocalStorageState<string | null>(LS_CHANNEL, {
    defaultValue: null,
  })
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setSandboxUser(user ?? 'anon')
  }, [setSandboxUser, user])

  const channels = useMemo<ChatItem[]>(() => {
    return serverState
      .filter(node => (node.meta?.type as string | undefined) === 'channel')
      .map(node => ({
        name: node.name,
        path: node.path,
        meta: toNodeMeta(node.meta, 'channel'),
        data: toNodeData(node.data),
      }))
      .sort(byPathDepth)
  }, [serverState])

  const messages = useMemo<ChatItem[]>(() => {
    const channel = activeChannel ?? null
    return serverState
      .filter(node => {
        if ((node.meta?.type as string | undefined) !== 'message') return false
        if (!channel) return false
        return node.path.startsWith(`pchat/channels/${channel}/`)
      })
      .map(node => ({
        name: node.name || lastSegment(node.path),
        path: node.path,
        meta: toNodeMeta(node.meta, 'message'),
        data: toNodeData(node.data),
      }))
      .filter(msg => !msg.data?._deleted)
      .sort(byPathDepth)
  }, [activeChannel, serverState])

  const state = useMemo<ChatState>(() => ({
    channels,
    messages,
    active_channel: activeChannel ?? null,
    user: user ?? 'anon',
    ts: new Date().toISOString(),
    source: 'sandbox',
  }), [activeChannel, channels, messages, user])

  const refresh = useCallback(async (channel?: string) => {
    const target = channel ?? activeChannel ?? undefined
    const result = await loadServerState(target)
    if (!result.ok) {
      setError(result.error ?? 'load failed')
      return
    }
    if (channel !== undefined) setActiveChannel(channel)
    setError(null)
  }, [activeChannel, loadServerState, setActiveChannel, user])

  const initialLoad = useCallback(async () => {
    setLoading(true)
    try {
      await refresh(activeChannel ?? undefined)
    } finally {
      setLoading(false)
    }
  }, [activeChannel, refresh])

  const selectChannel = useCallback(async (name: string) => {
    setActiveChannel(name)
    setLoading(true)
    try {
      const result = await serverExec(`/cselect ${name}`)
      if (!result.ok) {
        setError(result.error ?? 'select failed')
        return
      }
      await refresh(name)
    } finally {
      setLoading(false)
    }
  }, [refresh, serverExec, setActiveChannel])

  const postMessage = useCallback(async (text: string) => {
    const trimmed = text.trim()
    if (!trimmed) return
    setLoading(true)
    try {
      const result = await serverExec(`/cpost ${trimmed}`)
      if (!result.ok) {
        setError(result.error ?? 'post failed')
        return
      }
      await refresh()
    } finally {
      setLoading(false)
    }
  }, [refresh, serverExec])

  const createChannel = useCallback(async (name: string) => {
    const trimmed = name.trim()
    if (!trimmed) return
    setLoading(true)
    try {
      const result = await serverExec(`/cmkchannel ${trimmed}`)
      if (!result.ok) {
        setError(result.error ?? 'create failed')
        return
      }
      await refresh(trimmed)
    } finally {
      setLoading(false)
    }
  }, [refresh, serverExec])

  const toggleReaction = useCallback(async (msgId: string, emoji: string) => {
    setLoading(true)
    try {
      const result = await serverExec(`/creact ${msgId} ${emoji}`)
      if (!result.ok) {
        setError(result.error ?? 'reaction failed')
        return
      }
      await refresh()
    } finally {
      setLoading(false)
    }
  }, [refresh, serverExec])

  const exec = useCallback(async (cmd: string): Promise<{ result: CmdResult; local: boolean }> => {
    const normalized = cmd.trim().startsWith('/') ? cmd.trim() : `/${cmd.trim()}`
    const { op, args } = parseCmd(normalized)

    if (op === 'cselect' && args[0]) {
      await selectChannel(args[0])
      return { result: { ok: true, selected: args[0] }, local: false }
    }

    const result = await api.exec(normalized, user ?? 'anon')
    if (!result.error && !isReadOnlyOp(op)) {
      await refresh()
    }
    return { result, local: false }
  }, [refresh, selectChannel, user])

  useEffect(() => {
    initialLoad()
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  return {
    sandbox,
    state,
    channels,
    messages,
    activeChannel: activeChannel ?? null,
    user: user ?? 'anon',
    setUser,
    loading,
    error,
    refresh,
    selectChannel,
    postMessage,
    createChannel,
    toggleReaction,
    exec,
  }
}
