/**
 * useSandbox — React hook over Sandbox runtime.
 *
 * Single sandbox instance (singleton). All mutations through exec.
 * Components subscribe to sandbox changes reactively.
 *
 * Sandbox = client-side playground (can do anything locally).
 * Server interaction = only through serverExec (exec entries).
 */
import { useState, useEffect, useCallback, useMemo, useRef } from 'react'
import { Sandbox, type ExecResult } from '@/lib/sandbox'

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

  // Subscribe to sandbox changes — triggers re-render
  useEffect(() => {
    return sandbox.subscribe(() => setTick(t => t + 1))
  }, [sandbox])

  /** Local exec (sandbox-side, no server) */
  const exec = useCallback((op: string, args: Record<string, unknown> = {}): ExecResult => {
    return sandbox.exec(op, args, userRef.current)
  }, [sandbox])

  /** Server exec: send CMD to /api/pchat/exec, store result in exec log */
  const serverExec = useCallback(async (cmd: string): Promise<ExecResult> => {
    return sandbox.serverExec(cmd, userRef.current)
  }, [sandbox])

  /** Load server state (immutable snapshot) into sandbox tree */
  const loadServerState = useCallback(async (channel?: string): Promise<ExecResult> => {
    return sandbox.loadServerState(channel, userRef.current)
  }, [sandbox])

  /** Materialize containers (parallel) */
  const materializeAll = useCallback(async (...ids: string[]): Promise<void> => {
    await sandbox.materializeAll(...ids)
  }, [sandbox])

  return {
    sandbox,
    tree: sandbox.tree,
    execLog: sandbox.execLog,
    serverState: sandbox.serverState,
    fieldStore: sandbox.fieldStore,
    containers: sandbox.containers,

    exec,
    serverExec,
    loadServerState,
    materializeAll,

    resolve: sandbox.resolve.bind(sandbox),
    roots: sandbox.roots.bind(sandbox),
    children: sandbox.children.bind(sandbox),
    query: sandbox.query.bind(sandbox),
    allNodes: sandbox.allNodes.bind(sandbox),
    getField: sandbox.getField.bind(sandbox),
    getTableRows: sandbox.getTableRows.bind(sandbox),

    setUser: (u: string) => { userRef.current = u },
    user: userRef.current,
  }
}
