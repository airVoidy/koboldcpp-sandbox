'use client'

import { useState, useEffect, useRef, useCallback, type MouseEvent as ReactMouseEvent } from 'react'
import {
  Terminal, X, Minus, Plus, ChevronDown, ChevronRight,
  Eye, Link, Play, RefreshCw, FolderTree,
} from 'lucide-react'
import { exec as apiExec, getMessageProjection, getProjection } from '@/lib/api'
import { evaluate } from '@/lib/query'
import type { ChatState, CmdResult } from '@/types/chat'
import type { Projection, TemplateAggregation } from '@/types/runtime'
import { FSView } from './FSView'
import { ProjectionRenderer } from './ProjectionRenderer'
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

type TabKind = 'l0log' | 'inspector' | 'projection' | 'free' | 'shell' | 'objects' | 'fsview' | 'replay'

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

interface RuntimeRowView {
  rowId: string
  scopeId: string
  kind: 'intent' | 'reply' | 'live'
  entityId: string
  entityType: string
  localPath: string
  value: unknown
  valueType: string
}

interface ReplayDiffView {
  execAdded: string[]
  execRemoved: string[]
  nodesAdded: string[]
  nodesRemoved: string[]
  fieldsAdded: string[]
  fieldsRemoved: string[]
  rowsAdded: string[]
  rowsRemoved: string[]
}

interface TypedListEntryView {
  kind: string
  index: number
  role: 'template' | 'instance'
  virtual: boolean
  path: string
  node?: {
    type?: string
    meta: Record<string, unknown>
  }
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
  cyan:     '#66ccff',
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
        {result !== null && !error && (
          mode === 'value' ? <JsonTree data={result} /> : <PathView data={result} prefix={path} />
        )}
        {result === null && !error && (
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

function ProjectionTab() {
  const [nodePath, setNodePath] = useState('')
  const [projection, setProjection] = useState<Projection | null>(null)
  const [aggregation, setAggregation] = useState<TemplateAggregation | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const fetch_ = async () => {
    if (!nodePath.trim()) return
    setLoading(true)
    setError(null)
    setProjection(null)
    setAggregation(null)
    try {
      const target = nodePath.trim()
      const parsed = parseProjectionTarget(target)
      const { kind, value } = parsed
      if (kind === 'template') {
        const result = await getProjection(value, parsed.scope)
        if (isTemplateAggregation(result)) {
          setAggregation(result)
          return
        }
        setError('Projection response is not a template aggregation')
        return
      }

      const result = await getMessageProjection(value)
      if (isProjection(result)) {
        setProjection(result)
        return
      }
      setError('Projection response is not a message projection')
    } catch (e) {
      setError(String(e))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center gap-1 px-2 py-1" style={{ borderBottom: `1px solid ${TK.border}` }}>
        <input
          value={nodePath}
          onChange={(e) => setNodePath(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && fetch_()}
          placeholder="msg path or template type (e.g. pchat/channels/general/msg_1 or msg --scope=pchat/channels/general)"
          className="flex-1 px-2 py-0.5 rounded text-xs outline-none"
          style={{ background: TK.bg, color: TK.text, border: `1px solid ${TK.border}`, fontFamily: 'monospace' }}
        />
        <button onClick={fetch_} disabled={loading}
          className="flex items-center gap-1 px-2 py-0.5 rounded text-xs"
          style={{ background: TK.accent, color: '#fff' }}>
          <Play size={10} /> Load
        </button>
      </div>
      <div className="flex-1 overflow-y-auto p-1 text-[11px]" style={{ fontFamily: 'monospace' }}>
        {error && <div className="p-2" style={{ color: TK.err }}>{error}</div>}
        {projection && <ProjectionRenderer projection={projection} />}
        {aggregation && <AggregationRenderer aggregation={aggregation} />}
        {!projection && !aggregation && !error && (
          <div className="text-center py-4" style={{ color: TK.dim }}>Enter a node path and click Load</div>
        )}
      </div>
    </div>
  )
}

function AggregationRenderer({ aggregation }: { aggregation: TemplateAggregation }) {
  return (
    <div className="border border-[var(--border)] rounded-lg overflow-hidden">
      <div className="px-2 py-1 bg-[var(--surface)] text-[10px] flex items-center justify-between" style={{ color: TK.dim }}>
        <span>type: {aggregation.type}</span>
        <span>{aggregation.count} instances</span>
      </div>
      <table className="w-full text-[11px]">
        <thead>
          <tr className="bg-[var(--surface)] text-[var(--text-dim)]">
            <th className="text-left px-2 py-1 font-normal">instance</th>
            <th className="text-left px-2 py-1 font-normal">path</th>
            <th className="text-left px-2 py-1 font-normal">value</th>
            <th className="text-left px-2 py-1 font-normal w-16">hash</th>
          </tr>
        </thead>
        <tbody>
          {aggregation.fields.map((field) => (
            <tr key={field.namespaced_path} className="border-t border-[var(--border)] hover:bg-[var(--surface2)]">
              <td className="px-2 py-1 text-[var(--text-dim)]">{field.instance}</td>
              <td className="px-2 py-1 font-mono text-[var(--accent)]">{field.namespaced_path}</td>
              <td className="px-2 py-1 truncate max-w-[320px]">{formatProjectionValue(field.value)}</td>
              <td className="px-2 py-1 font-mono text-[var(--text-dim)] text-[9px]">{field.hash?.slice(0, 8)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {aggregation.fields.length === 0 && (
        <div className="px-3 py-4 text-center text-[var(--text-dim)] text-xs">
          No projected fields
        </div>
      )}
    </div>
  )
}

function parseProjectionTarget(input: string): { kind: 'message'; value: string } | { kind: 'template'; value: string; scope?: string } {
  const trimmed = input.trim()
  const scopeMatch = trimmed.match(/^([A-Za-z][\w-]*)(?:\s+--scope=(.+))?$/)
  if (scopeMatch && !trimmed.startsWith('msg_') && !trimmed.includes('/')) {
    return {
      kind: 'template',
      value: scopeMatch[1],
      scope: scopeMatch[2]?.trim() || undefined,
    }
  }
  return { kind: 'message', value: trimmed }
}

function isProjection(value: unknown): value is Projection {
  if (!value || typeof value !== 'object') return false
  const obj = value as Record<string, unknown>
  return typeof obj.source_node === 'string'
    && typeof obj.flat_store === 'object'
    && typeof obj.views === 'object'
}

function isTemplateAggregation(value: unknown): value is TemplateAggregation {
  if (!value || typeof value !== 'object') return false
  const obj = value as Record<string, unknown>
  return typeof obj.type === 'string'
    && typeof obj.count === 'number'
    && Array.isArray(obj.instances)
    && typeof obj.flat_store === 'object'
}

function formatProjectionValue(value: unknown): string {
  if (value === null || value === undefined) return 'null'
  if (typeof value === 'string') return value.length > 120 ? `${value.slice(0, 120)}...` : value
  if (typeof value === 'object') return JSON.stringify(value).slice(0, 120)
  return String(value)
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
      <FSView sandbox={sandbox} onSelect={(node, path) => {
        console.log('Selected:', path, node)
      }} />
    </div>
  )
}

function ObjectsTab() {
  const { allNodes, loadServerState, tree: runtimeTree, fieldStore } = useSandbox()
  const [tree, setTree] = useState<ObjectNode[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [expanded, setExpanded] = useState<Set<string>>(new Set())

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      if (runtimeTree.size === 0) {
        const result = await loadServerState()
        if (!result.ok) {
          setError(result.error ?? 'load failed')
          return
        }
      }
      const nodes = allNodes()
      const byPath = new Map(nodes.map(node => [node.path, node]))
      const roots = nodes.filter(node => !node.path.includes('/'))
      const walk = (nodePath: string): ObjectNode => {
        const node = byPath.get(nodePath)!
        return {
          name: node.name,
          type: String(node.type ?? 'node'),
          children: node.children.map(childPath => walk(childPath)),
        }
      }
      setTree(roots.map(node => walk(node.path)))
    } catch (e) {
      setError(String(e))
    } finally {
      setLoading(false)
    }
  }, [allNodes, loadServerState, runtimeTree.size])

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
        <span style={{ color: TK.dim }} className="ml-auto">
          {tree.length} roots · {runtimeTree.size} nodes · {fieldStore.size} fields
        </span>
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

function RuntimeObjectsTab() {
  const { allNodes, loadServerState, tree: runtimeTree, fieldStore, runtimeRows, runtimeBatches } = useSandbox()
  const [tree, setTree] = useState<ObjectNode[]>([])
  const [rows, setRows] = useState<RuntimeRowView[]>([])
  const [batches, setBatches] = useState<Record<string, RuntimeRowView[]>>({})
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [expanded, setExpanded] = useState<Set<string>>(new Set())
  const [mode, setMode] = useState<'tree' | 'rows' | 'batches'>('tree')

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      if (runtimeTree.size === 0) {
        const result = await loadServerState()
        if (!result.ok) {
          setError(result.error ?? 'load failed')
          return
        }
      }
      const nodes = allNodes()
      const byPath = new Map(nodes.map(node => [node.path, node]))
      const roots = nodes.filter(node => !node.path.includes('/'))
      const walk = (nodePath: string): ObjectNode => {
        const node = byPath.get(nodePath)!
        return {
          name: node.name,
          type: String(node.type ?? 'node'),
          children: node.children.map(childPath => walk(childPath)),
        }
      }
      setTree(roots.map(node => walk(node.path)))
      setRows(runtimeRows() as RuntimeRowView[])
      setBatches(runtimeBatches('entityId') as Record<string, RuntimeRowView[]>)
    } catch (e) {
      setError(String(e))
    } finally {
      setLoading(false)
    }
  }, [allNodes, loadServerState, runtimeBatches, runtimeRows, runtimeTree.size])

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
        <button
          onClick={() => setMode('tree')}
          className="px-1.5 py-0.5 rounded"
          style={{ background: mode === 'tree' ? TK.accent : TK.surface2, color: '#fff' }}>
          tree
        </button>
        <button
          onClick={() => setMode('rows')}
          className="px-1.5 py-0.5 rounded"
          style={{ background: mode === 'rows' ? TK.accent : TK.surface2, color: '#fff' }}>
          rows
        </button>
        <button
          onClick={() => setMode('batches')}
          className="px-1.5 py-0.5 rounded"
          style={{ background: mode === 'batches' ? TK.accent : TK.surface2, color: '#fff' }}>
          batches
        </button>
        <span style={{ color: TK.dim }} className="ml-auto">
          {tree.length} roots · {runtimeTree.size} nodes · {fieldStore.size} fields · {rows.length} rows
        </span>
      </div>
      <div className="flex-1 overflow-y-auto p-1 text-xs" style={{ fontFamily: 'monospace' }}>
        {error && <div className="p-2" style={{ color: TK.err }}>{error}</div>}
        {mode === 'tree' && tree.length === 0 && !error && !loading && (
          <div className="text-center py-4" style={{ color: TK.dim }}>No objects found</div>
        )}
        {mode === 'tree' && tree.map(n => renderNode(n, 0))}
        {mode === 'rows' && rows.map((row) => (
          <div key={row.rowId} className="py-0.5" style={{ borderBottom: `1px solid ${TK.border}22` }}>
            <div className="flex gap-2">
              <span style={{ color: TK.accent }}>{row.kind}</span>
              <span style={{ color: TK.dim }}>{row.entityType}</span>
              <span style={{ color: TK.text }}>{row.entityId}</span>
            </div>
            <div className="flex gap-2 pl-3">
              <span style={{ color: TK.cyan }}>{row.localPath}</span>
              <span style={{ color: TK.dim }}>=</span>
              <span style={{ color: TK.text }}>
                {typeof row.value === 'object' ? JSON.stringify(row.value) : String(row.value)}
              </span>
            </div>
          </div>
        ))}
        {mode === 'batches' && Object.entries(batches).map(([entityId, batch]) => (
          <div key={entityId} className="py-1" style={{ borderBottom: `1px solid ${TK.border}22` }}>
            <div className="flex gap-2">
              <span style={{ color: TK.accent }}>{entityId}</span>
              <span style={{ color: TK.dim }}>{batch.length} rows</span>
            </div>
            <div className="pl-3 text-[10px]" style={{ color: TK.dim }}>
              {batch.slice(0, 6).map(row => row.localPath).join(', ')}
              {batch.length > 6 ? ' …' : ''}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

function ReplayTab() {
  const { saveState, loadState, runFromSnapshot, execLog, tree, fieldStore, runtimeRows } = useSandbox()
  const [snapshot, setSnapshot] = useState<string>('')
  const [op, setOp] = useState('mk')
  const [argsText, setArgsText] = useState('{"parent":"pchat/channels","name":"tmp","type":"channel"}')
  const [result, setResult] = useState<unknown>(null)
  const [diff, setDiff] = useState<ReplayDiffView | null>(null)
  const [error, setError] = useState<string | null>(null)

  const handleCapture = () => {
    setSnapshot(JSON.stringify(saveState(), null, 2))
    setError(null)
  }

  const handleRestore = () => {
    try {
      const parsed = JSON.parse(snapshot)
      const restored = loadState(parsed)
      setResult(restored)
      setError(restored.ok ? null : (restored.error ?? 'restore failed'))
    } catch (e) {
      setError(String(e))
    }
  }

  const handleRun = () => {
    try {
      const parsedSnapshot = JSON.parse(snapshot)
      const parsedArgs = argsText.trim() ? JSON.parse(argsText) : {}
      const replay = runFromSnapshot(parsedSnapshot, op, parsedArgs, '_replay')
      setResult(replay.result)
      setDiff(replay.diff as ReplayDiffView)
      setError(replay.result.ok ? null : (replay.result.error ?? 'replay failed'))
    } catch (e) {
      setError(String(e))
    }
  }

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center gap-2 px-2 py-1 text-xs" style={{ borderBottom: `1px solid ${TK.border}` }}>
        <button onClick={handleCapture} className="px-1.5 py-0.5 rounded" style={{ background: TK.surface2, color: TK.text }}>
          Capture
        </button>
        <button onClick={handleRestore} className="px-1.5 py-0.5 rounded" style={{ background: TK.surface2, color: TK.text }}>
          Restore
        </button>
        <button onClick={handleRun} className="px-1.5 py-0.5 rounded" style={{ background: TK.accent, color: '#fff' }}>
          Run From Snapshot
        </button>
        <span style={{ color: TK.dim }} className="ml-auto">
          {execLog.length} exec · {tree.size} nodes · {fieldStore.size} fields · {runtimeRows().length} rows
        </span>
      </div>
      <div className="flex-1 overflow-y-auto p-2 text-xs" style={{ fontFamily: 'monospace' }}>
        {error && <div className="mb-2 p-2 rounded" style={{ color: TK.err, background: `${TK.err}11` }}>{error}</div>}

        <div className="mb-2">
          <div className="mb-1" style={{ color: TK.dim }}>op</div>
          <input
            value={op}
            onChange={(e) => setOp(e.target.value)}
            className="w-full px-2 py-1 rounded"
            style={{ background: TK.bg, color: TK.text, border: `1px solid ${TK.border}` }}
          />
        </div>

        <div className="mb-2">
          <div className="mb-1" style={{ color: TK.dim }}>args json</div>
          <textarea
            value={argsText}
            onChange={(e) => setArgsText(e.target.value)}
            className="w-full h-20 px-2 py-1 rounded"
            style={{ background: TK.bg, color: TK.text, border: `1px solid ${TK.border}` }}
          />
        </div>

        <div className="mb-2">
          <div className="mb-1" style={{ color: TK.dim }}>snapshot json</div>
          <textarea
            value={snapshot}
            onChange={(e) => setSnapshot(e.target.value)}
            className="w-full h-40 px-2 py-1 rounded"
            style={{ background: TK.bg, color: TK.text, border: `1px solid ${TK.border}` }}
          />
        </div>

        {result !== null && (
          <div className="mb-2">
            <div className="mb-1" style={{ color: TK.dim }}>result</div>
            <JsonTree data={result} />
          </div>
        )}

        {diff && (
          <div>
            <div className="mb-1" style={{ color: TK.dim }}>diff</div>
            <JsonTree data={diff} />
          </div>
        )}
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
                  { kind: 'replay' as const, label: 'Replay' },
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
            {currentTab?.kind === 'projection' && <ProjectionTab />}
            {currentTab?.kind === 'free' && <FreeTab chatState={chatState} />}
            {currentTab?.kind === 'shell' && <ShellTab exec={exec} />}
            {currentTab?.kind === 'objects' && <RuntimeObjectsTab />}
            {currentTab?.kind === 'replay' && <ReplayTab />}
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
