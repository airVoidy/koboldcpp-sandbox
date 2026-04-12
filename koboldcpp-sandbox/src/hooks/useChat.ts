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

  // Keep ref in sync — avoids stale closures
  const setState = useCallback((fn: ChatState | ((prev: ChatState) => ChatState)) => {
    _setState(prev => {
      const next = typeof fn === 'function' ? fn(prev) : fn
      stateRef.current = next
      return next
    })
  }, [])

  // Optimistic state updater for client-cmd
  const optimisticUpdate: StateUpdater = useCallback((fn) => {
    setState(prev => {
      const next = fn(prev)
      setCached(next) // persist to localStorage too
      return next
    })
  }, [setState, setCached])

  const activeChannel = state.active_channel

  // Fetch state from server — silent reconciliation, no loading flash
  const refresh = useCallback(async (channel?: string) => {
    try {
      const s = await api.getState(channel ?? activeChannel ?? undefined, user ?? 'anon')
      setState(s)
      setCached(s)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'fetch failed')
    }
  }, [activeChannel, user, setCached, setState])

  // Full refresh with loading indicator (initial load only)
  const initialLoad = useCallback(async () => {
    setLoading(true)
    await refresh()
    setLoading(false)
  }, [refresh])

  // ── Actions via client-cmd resolver ──

  const selectChannel = useCallback(async (name: string) => {
    // Pure optimistic — no loading, no flicker
    await execCmd(`/cselect ${name}`, user ?? 'anon', stateRef.current, optimisticUpdate)
  }, [user, optimisticUpdate])

  const postMessage = useCallback(async (text: string) => {
    if (!text.trim()) return
    await execCmd(`/cpost ${text}`, user ?? 'anon', stateRef.current, optimisticUpdate)
  }, [user, optimisticUpdate])

  const createChannel = useCallback(async (name: string) => {
    setLoading(true)
    try {
      await api.createChannel(name, user ?? 'anon')
      await refresh(name)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'create failed')
    } finally {
      setLoading(false)
    }
  }, [user, refresh])

  const toggleReaction = useCallback(async (msgId: string, emoji: string) => {
    // Pure optimistic — instant toggle, server confirms in background
    await execCmd(`/creact ${msgId} ${emoji}`, user ?? 'anon', stateRef.current, optimisticUpdate)
  }, [user, optimisticUpdate])

  // Run arbitrary CMD (for command palette)
  const exec = useCallback(async (cmd: string) => {
    return execCmd(cmd, user ?? 'anon', stateRef.current, optimisticUpdate)
  }, [user, optimisticUpdate])

  // Init: show cached immediately, reconcile from server in background
  useEffect(() => {
    if (cached) setState(cached)
    initialLoad()
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
