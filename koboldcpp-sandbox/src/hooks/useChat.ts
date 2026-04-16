/**
 * useChat — all actions through exec CMD.
 * Server = source of truth. No optimistic updates.
 */
import { useState, useCallback, useEffect, useRef } from 'react'
import { useLocalStorageState } from 'ahooks'
import type { ChatState } from '@/types/chat'
import { execCmd, type StateUpdater } from '@/lib/client-cmd'
import * as api from '@/lib/api'

const LS_KEY = 'pchat_state'
const LS_USER = 'pchat_user'

const EMPTY_STATE: ChatState = {
  channels: [],
  messages: [],
  active_channel: null,
  user: 'anon',
  ts: '',
}

export function useChat() {
  const [state, _setState] = useState<ChatState>(EMPTY_STATE)
  const [cached, setCached] = useLocalStorageState<ChatState>(LS_KEY, { defaultValue: EMPTY_STATE })
  const [user, setUser] = useLocalStorageState(LS_USER, { defaultValue: 'anon' })
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const stateRef = useRef(state)

  const setState = useCallback((fn: ChatState | ((prev: ChatState) => ChatState)) => {
    _setState(prev => {
      const next = typeof fn === 'function' ? fn(prev) : fn
      stateRef.current = next
      setCached(next)
      return next
    })
  }, [setCached])

  const stateUpdater: StateUpdater = useCallback((fn) => {
    setState(prev => fn(prev))
  }, [setState])

  const activeChannel = state.active_channel

  const refresh = useCallback(async (channel?: string) => {
    try {
      const s = await api.getState(channel ?? activeChannel ?? undefined, user ?? 'anon')
      setState(s)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'fetch failed')
    }
  }, [activeChannel, user, setState])

  // ── All actions through exec CMD ──

  const selectChannel = useCallback(async (name: string) => {
    await execCmd(`/cselect ${name}`, user ?? 'anon', stateRef.current, stateUpdater)
  }, [user, stateUpdater])

  const postMessage = useCallback(async (text: string) => {
    if (!text.trim()) return
    setLoading(true)
    await execCmd(`/cpost ${text}`, user ?? 'anon', stateRef.current, stateUpdater)
    setLoading(false)
  }, [user, stateUpdater])

  const createChannel = useCallback(async (name: string) => {
    setLoading(true)
    await execCmd(`/cmkchannel ${name}`, user ?? 'anon', stateRef.current, stateUpdater)
    setLoading(false)
  }, [user, stateUpdater])

  const toggleReaction = useCallback(async (msgId: string, emoji: string) => {
    await execCmd(`/creact ${msgId} ${emoji}`, user ?? 'anon', stateRef.current, stateUpdater)
  }, [user, stateUpdater])

  const exec = useCallback(async (cmd: string) => {
    return execCmd(cmd, user ?? 'anon', stateRef.current, stateUpdater)
  }, [user, stateUpdater])

  // Init: cached → immediate render, server → reconcile
  useEffect(() => {
    if (cached) setState(cached)
    setLoading(true)
    refresh().finally(() => setLoading(false))
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  return {
    state,
    channels: state.channels,
    messages: state.messages.filter(m => !m.data?._deleted),
    activeChannel,
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
