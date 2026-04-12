/**
 * useSandbox — React hook over Sandbox runtime.
 *
 * Single sandbox instance, all mutations through exec.
 * Components subscribe to sandbox changes reactively.
 */
import { useState, useEffect, useCallback, useMemo, useRef } from 'react'
import { Sandbox, type SandboxNode, type ExecResult } from '@/lib/sandbox'
import * as api from '@/lib/api'

/** Singleton sandbox */
let _sandbox: Sandbox | null = null
function getSandbox(): Sandbox {
  if (!_sandbox) _sandbox = new Sandbox()
  return _sandbox
}

export function useSandbox() {
  const sandbox = useMemo(() => getSandbox(), [])
  const [, setTick] = useState(0)
  const userRef = useRef('anon')

  // Subscribe to sandbox changes
  useEffect(() => {
    return sandbox.subscribe(() => setTick(t => t + 1))
  }, [sandbox])

  /** Local exec (sandbox-side, no server) */
  const exec = useCallback((op: string, args: Record<string, unknown>): ExecResult => {
    return sandbox.exec(op, args, userRef.current)
  }, [sandbox])

  /** Server exec + sync result into sandbox */
  const serverExec = useCallback(async (cmd: string): Promise<ExecResult> => {
    try {
      const result = await api.exec(cmd, userRef.current)
      // Sync: if server returned children/node data, update sandbox
      if (result.ok) {
        // Record as exec entry locally too
        sandbox.exec('_server_sync', { cmd, result }, userRef.current)
      }
      return { ok: true, data: result }
    } catch (e) {
      return { ok: false, error: e instanceof Error ? e.message : String(e) }
    }
  }, [sandbox])

  /** Load server state into sandbox */
  const loadFromServer = useCallback(async (channel?: string) => {
    try {
      const state = await api.getState(channel, userRef.current)

      // Build sandbox tree from server state
      // Ensure channels container
      if (!sandbox.root.children.has('channels')) {
        sandbox.exec('mk', { name: 'channels', type: 'channels' }, '_system')
      }
      const channelsNode = sandbox.root.children.get('channels')!

      // Sync channels
      for (const ch of state.channels ?? []) {
        const name = ch.meta?.name ?? ch.name
        if (!channelsNode.children.has(name)) {
          sandbox.exec('mkchannel', { name }, '_system')
        }
      }

      // Sync messages for active channel
      if (state.active_channel) {
        const chNode = channelsNode.children.get(state.active_channel)
        if (chNode) {
          for (const msg of state.messages ?? []) {
            if (!chNode.children.has(msg.name)) {
              sandbox.exec('post', {
                parent: `channels/${state.active_channel}`,
                content: msg.data?.content ?? '',
              }, msg.meta?.user ?? '_system')
              // Patch in actual data (reactions etc)
              const msgNode = chNode.children.get(msg.name)
              if (msgNode && msg.data) {
                Object.assign(msgNode.data, msg.data)
                Object.assign(msgNode.meta, msg.meta)
              }
            }
          }
        }
      }

      return { ok: true }
    } catch (e) {
      return { ok: false, error: e instanceof Error ? e.message : String(e) }
    }
  }, [sandbox])

  return {
    sandbox,
    root: sandbox.root,
    exec,
    serverExec,
    loadFromServer,
    execLog: sandbox.execLog,
    resolve: sandbox.resolve.bind(sandbox),
    flatten: sandbox.flatten.bind(sandbox),
    setUser: (u: string) => { userRef.current = u },
    user: userRef.current,
  }
}
