'use client'

import { useState, useEffect, useRef, useCallback, type MouseEvent as ReactMouseEvent } from 'react'
import {
  Terminal, X, Minus, Plus, ChevronDown, ChevronRight,
  Eye, Link, Play, RefreshCw, FolderTree,
} from 'lucide-react'
import { exec as apiExec } from '@/lib/api'
import { evaluate } from '@/lib/query'
import type { ChatState, CmdResult } from '@/types/chat'
import type { Projection, FieldEntry } from '@/types/runtime'
import { FSView } from './FSView'
import { useSandbox } from '@/hooks/useSandbox'

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

type ExecFn = (cmd: string) => Promise<{ result: CmdResult; local: boolean }>

interface DebugConsoleProps {
  visible: boolean
  onClose: () => void
  chatState: ChatState | null
  user: string
  exec: ExecFn
  initialTab?: string
}

type TabKind = 'l0log' | 'inspector' | 'projection' | 'free' | 'shell' | 'objects' | 'fsview'

interface TabDef {
  id: string
  label: string
  closable: boolean
  kind: TabKind
}

interface LogEntry {
  ts: string
  cmd: string
  ok: boolean
  error?: string
  raw: Record<string, unknown>
}

interface ShellEntry {
  cmd: string
  result: unknown
  ok: boolean
  ts: number
}

interface ObjectNode {
  name: string
  type: string
  children?: ObjectNode[]
}

/* ------------------------------------------------------------------ */
/*  Theme tokens (inline)                                              */
/* ------------------------------------------------------------------ */

const TK = {
  bg:       '#1a1a2e',
  surface:  '#222244',
  surface2: '#2a2a4a',
  border:   '#333366',
  text:     '#e0e0f0',
  dim:      '#8888aa',
  accent:   '#6c63ff',
  ok:       '#44dd88',
  err:      '#ff5566',
} as const

/* ------------------------------------------------------------------ */
/*  Helpers                                                            */
/* ------------------------------------------------------------------ */

/** Collapsible JSON tree renderer */
function JsonTree({ data, depth = 0 }: { data: unknown; depth?: number }) {
  const [open, setOpen] = useState(depth < 2)

  if (data === null || data === undefined) {
    return <span style={{ color: TK.dim }}>null</span>
  }
  if (typeof data === 'boolean') {
    return <span style={{ color: TK.accent }}>{String(data)}</span>
  }
  if (typeof data === 'number') {
    return <span style={{ color: '#ffcc66' }}>{data}</span>
  }
  if (typeof data === 'string') {
    return <span style={{ color: TK.ok }}>&quot;{data}&quot;</span>
  }

  if (Array.isArray(data)) {
    if (data.length === 0) return <span style={{ color: TK.dim }}>[]</span>
    return (
      <span>
        <button onClick={() => setOpen(!open)} className="inline mr-1" style={{ color: TK.accent }}>
          {open ? <ChevronDown size={12} className="inline" /> : <ChevronRight size={12} className="inline" />}
        </button>
        <span style={{ color: TK.dim }}>[{data.length}]</span>
        {open && (
          <div style={{ paddingLeft: 16 }}>
            {data.map((v, i) => (
              <div key={i}>
                <span style={{ color: TK.dim }}>{i}: </span>
                <JsonTree data={v} depth={depth + 1} />
              </div>
            ))}
          </div>
        )}
      </span>
    )
  }

  if (typeof data === 'object') {
    const keys = Object.keys(data as Record<string, unknown>)
    if (keys.length === 0) return <span style={{ color: TK.dim }}>{'{}'}</span>
    return (
      <span>
        <button onClick={() => setOpen(!open)} className="inline mr-1" style={{ color: TK.accent }}>
          {open ? <ChevronDown size={12} className="inline" /> : <ChevronRight size={12} className="inline" />}
        </button>
        <span style={{ color: TK.dim }}>{'{'}{keys.length}{'}'}</span>
        {open && (
          <div style={{ paddingLeft: 16 }}>
            {keys.map((k) => (
              <div key={k}>
                <span style={{ color: TK.accent }}>{k}</span>
                <span style={{ color: TK.dim }}>: </span>
                <JsonTree data={(data as Record<string, unknown>)[k]} depth={depth + 1} />
              </div>
            ))}
          </div>
        )}
      </span>
    )
  }

  return <span>{String(data)}</span>
}

/* --- L0 Log Tab --------------------------------------------------- */

function L0LogTab({ refreshInterval }: { refreshInterval: number }) {
  const [entries, setEntries] = useState<LogEntry[]>([])
  const [expanded, setExpanded] = useState<Set<number>>(new Set())
  const [loading, setLoading] = useState(false)
  const [autoRefresh, setAutoRefresh] = useState(true)
  const bottomRef = useRef<HTMLDivElement>(null)
  const scrollContainerRef = useRef<HTMLDivElement>(null)
  const isAtBottomRef = useRef(true)

  const fetchLogs = useCallback(async () => {
    try {
      setLoading(true)
      const res = await fetch('/api/endpoint-logs/exec?tail=100')
      if (!res.ok) return
      const data = await res.json()
      setEntries((Array.isArray(data) ? data : data.entries ?? []).map(
        (e: Record<string, unknown>) => {
          const req = (e.req ?? {}) as Record<string, unknown>
          return { ts: String(e.ts ?? ''), cmd: String(req.cmd ?? req.container_id ?? e.endpoint ?? ''),
            ok: e.ok !== false && !e.error, error: e.error ? String(e.error) : undefined, raw: e }
        },
      ))
    } catch { /* silent */ } finally { setLoading(false) }
  }, [])

  useEffect(() => { fetchLogs() }, [fetchLogs])
  useEffect(() => { if (!autoRefresh) return; const id = setInterval(fetchLogs, refreshInterval); return () => clearInterval(id) }, [autoRefresh, refreshInterval, fetchLogs])
  const handleScroll = useCallback(() => { const el = scrollContainerRef.current; if (el) isAtBottomRef.current = el.scrollHeight - el.scrollTop - el.clientHeight < 40 }, [])
  useEffect(() => { if (isAtBottomRef.current) bottomRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [entries])
  const toggle = (idx: number) => { setExpanded(prev => { const n = new Set(prev); n.has(idx) ? n.delete(idx) : n.add(idx); return n }) }

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center gap-2 px-2 py-1 text-xs" style={{ borderBottom: `1px solid ${TK.border}` }}>
        <button
          onClick={fetchLogs}
          className="flex items-center gap-1 px-1.5 py-0.5 rounded"
          style={{ background: TK.surface2, color: TK.text }}
        >
          <RefreshCw size={11} className={loading ? 'animate-spin' : ''} /> Refresh
        </button>
        <label className="flex items-center gap-1 cursor-pointer" style={{ color: TK.dim }}>
          <input
            type="checkbox"
            checked={autoRefresh}
            onChange={(e) => setAutoRefresh(e.target.checked)}
            className="accent-[#6c63ff]"
          />
          Auto ({refreshInterval / 1000}s)
        </label>
        <span style={{ color: TK.dim }} className="ml-auto">{entries.length} entries</span>
      </div>

      <div
        ref={scrollContainerRef}
        onScroll={handleScroll}
        className="flex-1 overflow-y-auto p-1 text-xs"
        style={{ fontFamily: 'monospace' }}
      >
        {entries.length === 0 && (
          <div className="text-center py-4" style={{ color: TK.dim }}>No log entries</div>
        )}
        {entries.map((e, i) => (
          <div key={i} className="py-0.5" style={{ borderBottom: `1px solid ${TK.border}22` }}>
            <div onClick={() => toggle(i)} className="flex items-center gap-2 cursor-pointer hover:opacity-80">
              {expanded.has(i)
                ? <ChevronDown size={10} style={{ color: TK.dim }} />
                : <ChevronRight size={10} style={{ color: TK.dim }} />}
              <span style={{ color: TK.dim, width: 72, flexShrink: 0, fontSize: 10 }}>
                {e.ts ? new Date(e.ts).toLocaleTimeString() : '--'}
              </span>
              <span
                className="font-bold text-[10px] w-6 text-center rounded"
                style={{
                  background: e.ok ? `${TK.ok}22` : `${TK.err}22`,
                  color: e.ok ? TK.ok : TK.err,
                }}
              >
                {e.ok ? 'OK' : 'ERR'}
              </span>
              <span className="truncate" style={{ color: TK.text }}>{e.cmd}</span>
            </div>
            {expanded.has(i) && (
              <div className="ml-6 mt-1 mb-1 p-1 rounded text-[11px] overflow-x-auto" style={{ background: TK.bg }}>
                <JsonTree data={e.raw} />
              </div>
            )}
          </div>
        ))}
        <div ref={bottomRef} />
      </div>
    </div>
  )
}

/* ------------------------------------------------------------------ */
/*  Tab content: Object Inspector                                      */
/* ------------------------------------------------------------------ */

function InspectorTab({ user }: { user: string }) {
  const [path, setPath] = useState('')
  const [result, setResult] = useState<unknown>(null)
  const [mode, setMode] = useState<'value' | 'path'>('value')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const resolve = async () => {
    if (!path.trim()) return
    setLoading(true)
    setError(null)
    try {
      const r = await apiExec(`/cat ${path.trim()}`, user)
      if (r.error) { setError(r.error); setResult(null) }
      else { setResult(r) }
    } catch (e) { setError(String(e)) }
    finally { setLoading(false) }
  }

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center gap-1 px-2 py-1" style={{ borderBottom: `1px solid ${TK.border}` }}>
        <input
          value={path}
          onChange={(e) => setPath(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && resolve()}
          placeholder="pchat/channels/general/msg_1"
          className="flex-1 px-2 py-0.5 rounded text-xs outline-none"
          style={{ background: TK.bg, color: TK.text, border: `1px solid ${TK.border}`, fontFamily: 'monospace' }}
        />
        <button onClick={resolve} disabled={loading}
          className="flex items-center gap-1 px-2 py-0.5 rounded text-xs"
          style={{ background: TK.accent, color: '#fff' }}>
          <Play size={10} /> Resolve
        </button>
        <button
          onClick={() => setMode(mode === 'value' ? 'path' : 'value')}
          className="flex items-center gap-1 px-1.5 py-0.5 rounded text-xs"
          style={{ background: TK.surface2, color: mode === 'path' ? TK.accent : TK.dim }}
          title={mode === 'value' ? 'Show path links' : 'Show values'}>
          {mode === 'value' ? <Eye size={10} /> : <Link size={10} />}
        </button>
      </div>
      <div className="flex-1 overflow-y-auto p-2 text-xs" style={{ fontFamily: 'monospace' }}>
        {error && <div style={{ color: TK.err }}>{error}</div>}
        {result && !error && (
          mode === 'value' ? <JsonTree data={result} /> : <PathView data={result} prefix={path} />
        )}
        {!result && !error && (
          <div className="text-center py-4" style={{ color: TK.dim }}>Enter a path and click Resolve</div>
        )}
      </div>
    </div>
  )
}

function PathView({ data, prefix }: { data: unknown; prefix: string }) {
  const paths = flattenPaths(data, prefix)
  return (
    <div>
      {paths.map(([p, v]) => (
        <div key={p} className="flex gap-2 py-0.5">
          <span style={{ color: TK.accent }}>{p}</span>
          <span style={{ color: TK.dim }}>=</span>
          <span style={{ color: TK.text }}>{typeof v === 'object' ? JSON.stringify(v) : String(v)}</span>
        </div>
      ))}
    </div>
  )
}

function flattenPaths(obj: unknown, prefix: string): [string, unknown][] {
  const result: [string, unknown][] = []
  const walk = (val: unknown, path: string) => {
    if (val === null || val === undefined || typeof val !== 'object') {
      result.push([path, val]); return
    }
    if (Array.isArray(val)) { val.forEach((v, i) => walk(v, `${path}[${i}]`)); return }
    for (const [k, v] of Object.entries(val as Record<string, unknown>)) walk(v, `${path}/${k}`)
  }
  walk(obj, prefix)
  return result
}

/* ------------------------------------------------------------------ */
/*  Tab content: Projection                                            */
/* ------------------------------------------------------------------ */

function ProjectionTab({ user }: { user: string }) {
  const [nodePath, setNodePath] = useState('')
  const [fields, setFields] = useState<Array<{ path: string; value: unknown; hash: string; type: string }>>([])
  const [mode, setMode] = useState<'value' | 'bind'>('value')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const fetch_ = async () => {
    if (!nodePath.trim()) return
    setLoading(true); setError(null)
    try {
      const r = await apiExec(`/query ${nodePath.trim()}`, user)
      if (r.error) { setError(r.error); return }
      const proj = (r as Record<string, unknown>).projection as Projection | undefined
      const store = proj?.flat_store ?? (r as Record<string, unknown>).flat_store as Record<string, FieldEntry> | undefined
      if (store) {
        setFields(Object.entries(store).map(([p, entry]) => ({
          path: p, value: entry[2], hash: String(entry[0]), type: typeof entry[2],
        })))
      } else { setFields([]); setError('No flat_store in response') }
    } catch (e) { setError(String(e)) }
    finally { setLoading(false) }
  }

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center gap-1 px-2 py-1" style={{ borderBottom: `1px solid ${TK.border}` }}>
        <input
          value={nodePath}
          onChange={(e) => setNodePath(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && fetch_()}
          placeholder="node path"
          className="flex-1 px-2 py-0.5 rounded text-xs outline-none"
          style={{ background: TK.bg, color: TK.text, border: `1px solid ${TK.border}`, fontFamily: 'monospace' }}
        />
        <button onClick={fetch_} disabled={loading}
          className="flex items-center gap-1 px-2 py-0.5 rounded text-xs"
          style={{ background: TK.accent, color: '#fff' }}>
          <Play size={10} /> Load
        </button>
        <button
          onClick={() => setMode(mode === 'value' ? 'bind' : 'value')}
          className="flex items-center gap-1 px-1.5 py-0.5 rounded text-xs"
          style={{ background: TK.surface2, color: mode === 'bind' ? TK.accent : TK.dim }}>
          {mode === 'value' ? <Eye size={10} /> : <Link size={10} />}
          {mode === 'value' ? 'Val' : 'Bind'}
        </button>
      </div>
      <div className="flex-1 overflow-y-auto p-1 text-[11px]" style={{ fontFamily: 'monospace' }}>
        {error && <div className="p-2" style={{ color: TK.err }}>{error}</div>}
        {fields.length > 0 && (
          <table className="w-full">
            <thead>
              <tr style={{ color: TK.dim, borderBottom: `1px solid ${TK.border}` }}>
                <th className="text-left px-1 py-0.5 font-normal">Path</th>
                <th className="text-left px-1 py-0.5 font-normal">{mode === 'value' ? 'Value' : 'Bind'}</th>
                <th className="text-left px-1 py-0.5 font-normal w-16">Hash</th>
                <th className="text-left px-1 py-0.5 font-normal w-12">Type</th>
              </tr>
            </thead>
            <tbody>
              {fields.map((f) => (
                <tr key={f.path} className="hover:opacity-80" style={{ borderBottom: `1px solid ${TK.border}11` }}>
                  <td className="px-1 py-0.5" style={{ color: TK.accent }}>{f.path}</td>
                  <td className="px-1 py-0.5 truncate max-w-[200px]" style={{ color: TK.text }}>
                    {typeof f.value === 'object' ? JSON.stringify(f.value) : String(f.value ?? '')}
                  </td>
                  <td className="px-1 py-0.5" style={{ color: TK.dim }}>{f.hash.slice(0, 8)}</td>
                  <td className="px-1 py-0.5" style={{ color: TK.dim }}>{f.type}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {fields.length === 0 && !error && (
          <div className="text-center py-4" style={{ color: TK.dim }}>Enter a node path and click Load</div>
        )}
      </div>
    </div>
  )
}

/* ------------------------------------------------------------------ */
/*  Tab content: Free (JSONata)                                        */
/* ------------------------------------------------------------------ */

function FreeTab({ chatState }: { chatState: ChatState | null }) {
  const [expr, setExpr] = useState('')
  const [result, setResult] = useState<unknown>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  const run = async () => {
    if (!expr.trim()) return
    setLoading(true); setError(null)
    try { setResult(await evaluate(expr, chatState ?? {})) }
    catch (e) { setError(String(e)); setResult(null) }
    finally { setLoading(false) }
  }

  return (
    <div className="flex flex-col h-full">
      <div className="px-2 py-1" style={{ borderBottom: `1px solid ${TK.border}` }}>
        <div className="flex items-center gap-1">
          <textarea
            value={expr}
            onChange={(e) => setExpr(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) { e.preventDefault(); run() }
            }}
            placeholder="JSONata expression  (Ctrl+Enter to eval)"
            rows={3}
            className="flex-1 px-2 py-1 rounded text-xs outline-none resize-y"
            style={{ background: TK.bg, color: TK.text, border: `1px solid ${TK.border}`, fontFamily: 'monospace' }}
          />
          <button onClick={run} disabled={loading}
            className="flex items-center gap-1 px-2 py-1 rounded text-xs self-end"
            style={{ background: TK.accent, color: '#fff' }}>
            <Play size={10} /> Eval
          </button>
        </div>
        <div className="text-[10px] mt-0.5" style={{ color: TK.dim }}>
          Input = chatState ({chatState ? `${chatState.messages?.length ?? 0} msgs` : 'null'})
        </div>
      </div>
      <div className="flex-1 overflow-y-auto p-2 text-xs" style={{ fontFamily: 'monospace' }}>
        {error && <div style={{ color: TK.err }}>{error}</div>}
        {result !== null && !error && <JsonTree data={result} />}
        {result === null && !error && (
          <div className="text-center py-4" style={{ color: TK.dim }}>
            Write a JSONata expression and press Ctrl+Enter
          </div>
        )}
      </div>
    </div>
  )
}

/* ------------------------------------------------------------------ */
/*  Tab content: Shell (merged CommandPalette)                         */
/* ------------------------------------------------------------------ */

const QUICK_COMMANDS = ['/wiki status', '/wiki list', '/dir', '/cat', '/mproject msg']

function ShellTab({ exec }: { exec: ExecFn }) {
  const [input, setInput] = useState('')
  const [history, setHistory] = useState<ShellEntry[]>([])
  const [histIdx, setHistIdx] = useState(-1)
  const [expanded, setExpanded] = useState<Set<number>>(new Set())
  const bottomRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [history])

  useEffect(() => {
    inputRef.current?.focus()
  }, [])

  const runCmd = async (cmd: string) => {
    if (!cmd.trim()) return
    const trimmed = cmd.trim()
    const cmdStr = trimmed.startsWith('/') ? trimmed : `/${trimmed}`
    try {
      const { result: r, local } = await exec(cmdStr)
      setHistory(prev => [...prev, {
        cmd: cmdStr, result: { ...r, _local: local }, ok: r.ok !== false && !r.error, ts: Date.now(),
      }])
    } catch (e: unknown) {
      setHistory(prev => [...prev, {
        cmd: cmdStr, result: { error: e instanceof Error ? e.message : String(e) },
        ok: false, ts: Date.now(),
      }])
    }
    setInput('')
    setHistIdx(-1)
  }

  const handleKey = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      e.preventDefault()
      runCmd(input)
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      const cmds = history.map(h => h.cmd)
      if (cmds.length === 0) return
      const next = histIdx === -1 ? cmds.length - 1 : Math.max(0, histIdx - 1)
      setHistIdx(next)
      setInput(cmds[next])
    } else if (e.key === 'ArrowDown') {
      e.preventDefault()
      const cmds = history.map(h => h.cmd)
      if (histIdx === -1) return
      const next = histIdx + 1
      if (next >= cmds.length) { setHistIdx(-1); setInput('') }
      else { setHistIdx(next); setInput(cmds[next]) }
    }
  }

  const toggleResult = (idx: number) => {
    setExpanded(prev => {
      const next = new Set(prev)
      next.has(idx) ? next.delete(idx) : next.add(idx)
      return next
    })
  }

  return (
    <div className="flex flex-col h-full" style={{ fontFamily: '"JetBrains Mono", "Fira Code", monospace' }}>
      {/* output area */}
      <div className="flex-1 overflow-y-auto p-2 text-xs">
        {history.length === 0 && (
          <div className="mb-3">
            <div className="text-[10px] uppercase mb-1" style={{ color: TK.dim }}>Quick commands</div>
            {QUICK_COMMANDS.map(cmd => (
              <button key={cmd} onClick={() => runCmd(cmd)}
                className="block px-2 py-0.5 rounded text-left hover:opacity-80 w-full text-xs mb-0.5"
                style={{ color: TK.accent, background: `${TK.surface2}88` }}>
                {cmd}
              </button>
            ))}
          </div>
        )}

        {history.map((entry, i) => (
          <div key={i} className="mb-2">
            <div className="flex items-center gap-1">
              <span style={{ color: TK.accent }}>$</span>
              <span style={{ color: TK.text }}>{entry.cmd}</span>
              <span className="text-[9px] ml-auto" style={{ color: TK.dim }}>
                {new Date(entry.ts).toLocaleTimeString()}
              </span>
            </div>
            <div className="ml-3 mt-0.5">
              {entry.ok ? (
                <div>
                  <button onClick={() => toggleResult(i)}
                    className="inline mr-1" style={{ color: TK.ok }}>
                    {expanded.has(i)
                      ? <ChevronDown size={10} className="inline" />
                      : <ChevronRight size={10} className="inline" />}
                  </button>
                  <span className="text-[10px]" style={{ color: TK.ok }}>OK</span>
                  {/* Always show result by default, toggle collapses it */}
                  {(!expanded.has(i)) && (
                    <div className="mt-1 p-1 rounded overflow-x-auto" style={{ background: TK.bg }}>
                      <JsonTree data={entry.result} />
                    </div>
                  )}
                </div>
              ) : (
                <div>
                  <span className="text-[10px]" style={{ color: TK.err }}>
                    ERR: {(entry.result as Record<string, unknown>)?.error as string ?? 'unknown'}
                  </span>
                  <button onClick={() => toggleResult(i)}
                    className="inline ml-1" style={{ color: TK.dim }}>
                    {expanded.has(i) ? <ChevronDown size={10} className="inline" /> : <ChevronRight size={10} className="inline" />}
                  </button>
                  {expanded.has(i) && (
                    <div className="mt-1 p-1 rounded overflow-x-auto" style={{ background: TK.bg }}>
                      <JsonTree data={entry.result} />
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
        ))}
        <div ref={bottomRef} />
      </div>

      {/* input line */}
      <div className="flex items-center gap-2 px-2 py-1.5 shrink-0"
        style={{ borderTop: `1px solid ${TK.border}`, background: TK.bg }}>
        <span style={{ color: TK.accent, fontSize: 11 }}>$</span>
        <input
          ref={inputRef}
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={handleKey}
          placeholder="/command..."
          className="flex-1 bg-transparent text-xs outline-none"
          style={{ color: TK.text, caretColor: TK.accent }}
        />
      </div>
    </div>
  )
}

/* ------------------------------------------------------------------ */
/*  Tab content: Object List                                           */
/* ------------------------------------------------------------------ */

function FSViewTab() {
  const { sandbox, loadServerState } = useSandbox()
  const [loaded, setLoaded] = useState(false)

  useEffect(() => {
    if (!loaded) {
      loadServerState().then(() => setLoaded(true))
    }
  }, [loaded, loadServerState])

  return (
    <div className="h-full overflow-hidden">
      <FSView sandbox={sandbox} onSelect={(_node, path) => {
        console.log('FS selected:', path)
      }} />
    </div>
  )
}

function ObjectsTab({ exec }: { exec: ExecFn }) {
  const [tree, setTree] = useState<ObjectNode[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [expanded, setExpanded] = useState<Set<string>>(new Set())

  const load = useCallback(async () => {
    setLoading(true); setError(null)
    try {
      const { result } = await exec('/dir')
      if (result.error) { setError(result.error); return }
      // parse result into tree nodes - result may have items, children, or be a flat list
      const raw = result as Record<string, unknown>
      const items = (raw.items ?? raw.children ?? raw.entries ?? Object.keys(raw).filter(k => k !== 'ok')) as unknown
      if (Array.isArray(items)) {
        setTree(items.map((it: unknown) => {
          if (typeof it === 'string') return { name: it, type: 'node' }
          const obj = it as Record<string, unknown>
          return {
            name: String(obj.name ?? obj.id ?? obj.path ?? '?'),
            type: String(obj.type ?? 'node'),
            children: Array.isArray(obj.children)
              ? (obj.children as Record<string, unknown>[]).map(c => ({
                  name: String(c.name ?? c.id ?? '?'),
                  type: String(c.type ?? 'node'),
                }))
              : undefined,
          }
        }))
      } else {
        // fallback: show raw keys as nodes
        setTree(Object.keys(raw).filter(k => k !== 'ok').map(k => ({ name: k, type: typeof raw[k] === 'object' ? 'dir' : 'leaf' })))
      }
    } catch (e) { setError(String(e)) }
    finally { setLoading(false) }
  }, [exec])

  useEffect(() => { load() }, [load])

  const toggle = (name: string) => {
    setExpanded(prev => {
      const next = new Set(prev)
      next.has(name) ? next.delete(name) : next.add(name)
      return next
    })
  }

  const renderNode = (node: ObjectNode, depth: number) => (
    <div key={`${depth}-${node.name}`} style={{ paddingLeft: depth * 14 }}>
      <div className="flex items-center gap-1 py-0.5 cursor-pointer hover:opacity-80"
        onClick={() => node.children && toggle(node.name)}>
        {node.children ? (
          expanded.has(node.name)
            ? <ChevronDown size={10} style={{ color: TK.dim }} />
            : <ChevronRight size={10} style={{ color: TK.dim }} />
        ) : <span className="w-[10px]" />}
        <FolderTree size={10} style={{ color: TK.accent }} />
        <span style={{ color: TK.text }} className="text-xs">{node.name}</span>
        <span className="text-[9px]" style={{ color: TK.dim }}>{node.type}</span>
      </div>
      {node.children && expanded.has(node.name) &&
        node.children.map(c => renderNode(c, depth + 1))
      }
    </div>
  )

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center gap-2 px-2 py-1 text-xs" style={{ borderBottom: `1px solid ${TK.border}` }}>
        <button onClick={load}
          className="flex items-center gap-1 px-1.5 py-0.5 rounded"
          style={{ background: TK.surface2, color: TK.text }}>
          <RefreshCw size={11} className={loading ? 'animate-spin' : ''} /> Refresh
        </button>
        <span style={{ color: TK.dim }} className="ml-auto">{tree.length} roots</span>
      </div>
      <div className="flex-1 overflow-y-auto p-1 text-xs" style={{ fontFamily: 'monospace' }}>
        {error && <div className="p-2" style={{ color: TK.err }}>{error}</div>}
        {tree.length === 0 && !error && !loading && (
          <div className="text-center py-4" style={{ color: TK.dim }}>No objects found</div>
        )}
        {tree.map(n => renderNode(n, 0))}
      </div>
    </div>
  )
}

/* ------------------------------------------------------------------ */
/*  Main component                                                     */
/* ------------------------------------------------------------------ */

const DEFAULT_TABS: TabDef[] = [
  { id: 'l0log', label: 'L0 Log', closable: false, kind: 'l0log' },
  { id: 'shell', label: 'Shell', closable: false, kind: 'shell' },
]

let tabCounter = 0
function nextTabId() { return `tab_${++tabCounter}` }

export function DebugConsole({ visible, onClose, chatState, user, exec, initialTab }: DebugConsoleProps) {
  const [pos, setPos] = useState({ x: 80, y: 60 })
  const [size, setSize] = useState({ w: 560, h: 420 })
  const [minimized, setMinimized] = useState(false)
  const [tabs, setTabs] = useState<TabDef[]>(DEFAULT_TABS)
  const [activeTab, setActiveTab] = useState('l0log')
  const [refreshInterval] = useState(3000)

  /* handle initialTab prop changes (e.g. Ctrl+K -> shell) */
  const prevInitialTab = useRef(initialTab)
  useEffect(() => {
    if (initialTab && initialTab !== prevInitialTab.current && visible) {
      setActiveTab(initialTab)
      setMinimized(false)
    }
    prevInitialTab.current = initialTab
  }, [initialTab, visible])

  /* drag state */
  const dragRef = useRef<{ startX: number; startY: number; posX: number; posY: number } | null>(null)
  const resizeRef = useRef<{ startX: number; startY: number; w: number; h: number } | null>(null)

  const onDragStart = (e: ReactMouseEvent) => {
    e.preventDefault()
    dragRef.current = { startX: e.clientX, startY: e.clientY, posX: pos.x, posY: pos.y }
    const onMove = (ev: globalThis.MouseEvent) => {
      if (!dragRef.current) return
      setPos({ x: dragRef.current.posX + ev.clientX - dragRef.current.startX, y: dragRef.current.posY + ev.clientY - dragRef.current.startY })
    }
    const onUp = () => { dragRef.current = null; document.removeEventListener('mousemove', onMove); document.removeEventListener('mouseup', onUp) }
    document.addEventListener('mousemove', onMove)
    document.addEventListener('mouseup', onUp)
  }

  const onResizeStart = (e: ReactMouseEvent) => {
    e.preventDefault(); e.stopPropagation()
    resizeRef.current = { startX: e.clientX, startY: e.clientY, w: size.w, h: size.h }
    const onMove = (ev: globalThis.MouseEvent) => {
      if (!resizeRef.current) return
      setSize({ w: Math.max(320, resizeRef.current.w + ev.clientX - resizeRef.current.startX), h: Math.max(200, resizeRef.current.h + ev.clientY - resizeRef.current.startY) })
    }
    const onUp = () => { resizeRef.current = null; document.removeEventListener('mousemove', onMove); document.removeEventListener('mouseup', onUp) }
    document.addEventListener('mousemove', onMove)
    document.addEventListener('mouseup', onUp)
  }

  /* keyboard shortcut: Ctrl+Shift+D to toggle */
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.ctrlKey && e.shiftKey && e.key === 'D') { e.preventDefault(); onClose() }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [onClose])

  /* tab management */
  const addTab = (kind: TabKind, label: string) => {
    const id = nextTabId()
    setTabs(prev => [...prev, { id, label, closable: true, kind }])
    setActiveTab(id)
  }

  const closeTab = (id: string) => {
    setTabs(prev => prev.filter(t => t.id !== id))
    if (activeTab === id) setActiveTab(tabs[0]?.id ?? 'l0log')
  }

  const currentTab = tabs.find(t => t.id === activeTab) ?? tabs[0]

  if (!visible) return null

  return (
    <div
      className="fixed z-[9999] flex flex-col rounded-lg overflow-hidden shadow-2xl"
      style={{
        left: pos.x, top: pos.y,
        width: minimized ? 280 : size.w,
        height: minimized ? 32 : size.h,
        background: TK.surface,
        border: `1px solid ${TK.border}`,
        fontFamily: '"JetBrains Mono", "Fira Code", "Cascadia Code", monospace',
        fontSize: 12, color: TK.text,
      }}
    >
      {/* title bar */}
      <div onMouseDown={onDragStart}
        className="flex items-center gap-2 px-2 py-1 cursor-move select-none shrink-0"
        style={{ background: TK.bg, borderBottom: `1px solid ${TK.border}` }}>
        <Terminal size={13} style={{ color: TK.accent }} />
        <span className="text-xs font-bold" style={{ color: TK.accent }}>Debug Console</span>
        <span className="text-[10px]" style={{ color: TK.dim }}>Ctrl+Shift+D</span>
        <div className="flex-1" />
        <button onClick={() => setMinimized(!minimized)} className="p-0.5 rounded hover:opacity-70" style={{ color: TK.dim }} title="Minimize">
          <Minus size={12} />
        </button>
        <button onClick={onClose} className="p-0.5 rounded hover:opacity-70" style={{ color: TK.err }} title="Close">
          <X size={12} />
        </button>
      </div>

      {!minimized && (
        <>
          {/* tab bar */}
          <div className="flex items-center gap-0 px-1 shrink-0 overflow-x-auto"
            style={{ background: TK.surface2, borderBottom: `1px solid ${TK.border}` }}>
            {tabs.map(t => (
              <div key={t.id}
                className="flex items-center gap-1 px-2 py-1 text-[11px] cursor-pointer shrink-0"
                style={{
                  background: activeTab === t.id ? TK.surface : 'transparent',
                  color: activeTab === t.id ? TK.text : TK.dim,
                  borderBottom: activeTab === t.id ? `2px solid ${TK.accent}` : '2px solid transparent',
                }}
                onClick={() => setActiveTab(t.id)}>
                {t.label}
                {t.closable && (
                  <button onClick={e => { e.stopPropagation(); closeTab(t.id) }}
                    className="ml-0.5 hover:opacity-70" style={{ color: TK.dim }}>
                    <X size={9} />
                  </button>
                )}
              </div>
            ))}
            {/* add-tab dropdown */}
            <div className="relative group">
              <button className="px-1.5 py-1 text-[11px] hover:opacity-70" style={{ color: TK.dim }} title="Add tab">
                <Plus size={12} />
              </button>
              <div className="absolute left-0 top-full hidden group-hover:flex flex-col py-1 rounded shadow-lg z-10"
                style={{ background: TK.bg, border: `1px solid ${TK.border}`, minWidth: 140 }}>
                {([
                  { kind: 'inspector' as const, label: 'Object Inspector' },
                  { kind: 'projection' as const, label: 'Projection' },
                  { kind: 'free' as const, label: 'JSONata (Free)' },
                  { kind: 'objects' as const, label: 'Object List' },
                  { kind: 'fsview' as const, label: 'FS View' },
                  { kind: 'l0log' as const, label: 'L0 Log' },
                  { kind: 'shell' as const, label: 'Shell' },
                ] as const).map(({ kind, label }) => (
                  <button key={kind} className="text-left px-3 py-1 text-[11px] hover:opacity-80"
                    style={{ color: TK.text }} onClick={() => addTab(kind, label)}>
                    {label}
                  </button>
                ))}
              </div>
            </div>
          </div>

          {/* tab content */}
          <div className="flex-1 min-h-0 overflow-hidden">
            {currentTab?.kind === 'l0log' && <L0LogTab refreshInterval={refreshInterval} />}
            {currentTab?.kind === 'inspector' && <InspectorTab user={user} />}
            {currentTab?.kind === 'projection' && <ProjectionTab user={user} />}
            {currentTab?.kind === 'free' && <FreeTab chatState={chatState} />}
            {currentTab?.kind === 'shell' && <ShellTab exec={exec} />}
            {currentTab?.kind === 'objects' && <ObjectsTab exec={exec} />}
            {currentTab?.kind === 'fsview' && <FSViewTab />}
          </div>

          {/* resize handle */}
          <div onMouseDown={onResizeStart}
            className="absolute bottom-0 right-0 w-4 h-4 cursor-nwse-resize" style={{ opacity: 0.4 }}>
            <svg width="16" height="16" viewBox="0 0 16 16">
              <path d="M14 14L14 8M14 14L8 14" stroke={TK.dim} strokeWidth="1.5" fill="none" />
              <path d="M14 14L14 11M14 14L11 14" stroke={TK.dim} strokeWidth="1.5" fill="none" />
            </svg>
          </div>
        </>
      )}
    </div>
  )
}

export default DebugConsole
