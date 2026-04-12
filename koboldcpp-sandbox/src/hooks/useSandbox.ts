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

let _sandbox: Sandbox | null = null
function getSandbox(): Sandbox {
  if (!_sandbox) _sandbox = new Sandbox()
  return _sandbox
}

export function useSandbox() {
  const sandbox = useMemo(() => getSandbox(), [])
  const [, setTick] = useState(0)
  const userRef = useRef('anon')

  useEffect(() => {
    return sandbox.subscribe(() => setTick(t => t + 1))
  }, [sandbox])

  const exec = useCallback((op: string, args: Record<string, unknown> = {}): ExecResult => {
    return sandbox.exec(op, args, userRef.current)
  }, [sandbox])

  const serverExec = useCallback(async (cmd: string): Promise<ExecResult> => {
    return sandbox.serverExec(cmd, userRef.current)
  }, [sandbox])

  const loadServerState = useCallback(async (channel?: string): Promise<ExecResult> => {
    return sandbox.loadServerState(channel, userRef.current)
  }, [sandbox])

  return {
    sandbox,
    tree: sandbox.tree,
    execLog: sandbox.execLog,
    serverState: sandbox.serverState,
    fieldStore: sandbox.fieldStore,

    exec,
    serverExec,
    loadServerState,

    resolve: sandbox.resolve.bind(sandbox),
    roots: sandbox.roots.bind(sandbox),
    children: sandbox.children.bind(sandbox),
    childListKinds: sandbox.childListKinds.bind(sandbox),
    childrenByKind: sandbox.childrenByKind.bind(sandbox),
    query: sandbox.query.bind(sandbox),
    allNodes: sandbox.allNodes.bind(sandbox),
    getEntry: sandbox.getEntry.bind(sandbox),
    getField: sandbox.getField.bind(sandbox),
    queryFields: sandbox.queryFields.bind(sandbox),

    setUser: (u: string) => { userRef.current = u },
    user: userRef.current,
  }
}
