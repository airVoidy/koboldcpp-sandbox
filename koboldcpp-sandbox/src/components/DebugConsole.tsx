'use client'

import { useState, useEffect, useRef, useCallback, type MouseEvent as ReactMouseEvent } from 'react'
import {
  Terminal, X, Minus, Plus, ChevronDown, ChevronRight,
  Eye, Link, Play, RefreshCw,
} from 'lucide-react'
import { exec, getProjection } from '@/lib/api'
import { evaluate } from '@/lib/query'
import type { ChatState } from '@/types/chat'
import type { Projection, FieldEntry } from '@/types/runtime'

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

interface DebugConsoleProps {
  visible: boolean
  onClose: () => void
  chatState: ChatState | null
  user: string
}

interface TabDef {
  id: string
  label: string
  closable: boolean
  kind: 'l0log' | 'inspector' | 'projection' | 'free'
}

interface LogEntry {
  ts: string
  cmd: string
  ok: boolean
  error?: string
  raw: Record<string, unknown>
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

function cls(...parts: (string | false | undefined | null)[]) {
  return parts.filter(Boolean).join(' ')
}

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

/* ------------------------------------------------------------------ */
/*  Tab content: L0 Log                                                */
/* ------------------------------------------------------------------ */

function L0LogTab({ refreshInterval }: { refreshInterval: number }) {
  const [entries, setEntries] = useState<LogEntry[]>([])
  const [expanded, setExpanded] = useState<Set<number>>(new Set())
  const [loading, setLoading] = useState(false)
  const [autoRefresh, setAutoRefresh] = useState(true)
  const bottomRef = useRef<HTMLDivElement>(null)

  const fetchLogs = useCallback(async () => {
    try {
      setLoading(true)
      const res = await fetch('/api/endpoint-logs/exec?tail=100')
      if (!res.ok) return
      const data = await res.json()
      const items: LogEntry[] = (Array.isArray(data) ? data : data.entries ?? []).map(
        (e: Record<string, unknown>) => {
          const req = (e.req ?? {}) as Record<string, unknown>
          return {
            ts: String(e.ts ?? ''),
            cmd: String(req.cmd ?? req.container_id ?? e.endpoint ?? ''),
            ok: e.ok !== false && !e.error,
            error: e.error ? String(e.error) : undefined,
            raw: e,
          }
        },
      )
      setEntries(items)
    } catch {
      /* silent */
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchLogs()
  }, [fetchLogs])

  useEffect(() => {
    if (!autoRefresh) return
    const id = setInterval(fetchLogs, refreshInterval)
    return () => clearInterval(id)
  }, [autoRefresh, refreshInterval, fetchLogs])

  // Smart scroll: only auto-scroll if user is already at bottom
  const scrollContainerRef = useRef<HTMLDivElement>(null)
  const isAtBottomRef = useRef(true)

  const handleScroll = useCallback(() => {
    const el = scrollContainerRef.current
    if (!el) return
    const threshold = 40
    isAtBottomRef.current = el.scrollHeight - el.scrollTop - el.clientHeight < threshold
  }, [])

  useEffect(() => {
    if (isAtBottomRef.current) {
      bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
    }
  }, [entries])

  const toggle = (idx: number) => {
    setExpanded((prev) => {
      const next = new Set(prev)
      next.has(idx) ? next.delete(idx) : next.add(idx)
      return next
    })
  }

  return (
    <div className="flex flex-col h-full">
      {/* toolbar */}
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

      {/* log list */}
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
            <div
              onClick={() => toggle(i)}
              className="flex items-center gap-2 cursor-pointer hover:opacity-80"
            >
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
      const r = await exec(`/cat ${path.trim()}`, user)
      if (r.error) {
        setError(r.error)
        setResult(null)
      } else {
        setResult(r)
      }
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
          value={path}
          onChange={(e) => setPath(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && resolve()}
          placeholder="pchat/channels/general/msg_1"
          className="flex-1 px-2 py-0.5 rounded text-xs outline-none"
          style={{ background: TK.bg, color: TK.text, border: `1px solid ${TK.border}`, fontFamily: 'monospace' }}
        />
        <button
          onClick={resolve}
          disabled={loading}
          className="flex items-center gap-1 px-2 py-0.5 rounded text-xs"
          style={{ background: TK.accent, color: '#fff' }}
        >
          <Play size={10} /> Resolve
        </button>
        <button
          onClick={() => setMode(mode === 'value' ? 'path' : 'value')}
          className="flex items-center gap-1 px-1.5 py-0.5 rounded text-xs"
          style={{ background: TK.surface2, color: mode === 'path' ? TK.accent : TK.dim }}
          title={mode === 'value' ? 'Show path links' : 'Show values'}
        >
          {mode === 'value' ? <Eye size={10} /> : <Link size={10} />}
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-2 text-xs" style={{ fontFamily: 'monospace' }}>
        {error && <div style={{ color: TK.err }}>{error}</div>}
        {result && !error && (
          mode === 'value'
            ? <JsonTree data={result} />
            : <PathView data={result} prefix={path} />
        )}
        {!result && !error && (
          <div className="text-center py-4" style={{ color: TK.dim }}>
            Enter a path and click Resolve
          </div>
        )}
      </div>
    </div>
  )
}

/** Flat canonical path listing for path-link mode */
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
      result.push([path, val])
      return
    }
    if (Array.isArray(val)) {
      val.forEach((v, i) => walk(v, `${path}[${i}]`))
      return
    }
    for (const [k, v] of Object.entries(val as Record<string, unknown>)) {
      walk(v, `${path}/${k}`)
    }
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
    setLoading(true)
    setError(null)
    try {
      const r = await exec(`/query ${nodePath.trim()}`, user)
      if (r.error) { setError(r.error); return }
      // extract flat_store or fields from result
      const proj = (r as Record<string, unknown>).projection as Projection | undefined
      const store = proj?.flat_store ?? (r as Record<string, unknown>).flat_store as Record<string, FieldEntry> | undefined
      if (store) {
        setFields(
          Object.entries(store).map(([p, entry]) => ({
            path: p,
            value: entry[2],
            hash: String(entry[0]),
            type: typeof entry[2],
          })),
        )
      } else {
        setFields([])
        setError('No flat_store in response')
      }
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
          placeholder="node path"
          className="flex-1 px-2 py-0.5 rounded text-xs outline-none"
          style={{ background: TK.bg, color: TK.text, border: `1px solid ${TK.border}`, fontFamily: 'monospace' }}
        />
        <button
          onClick={fetch_}
          disabled={loading}
          className="flex items-center gap-1 px-2 py-0.5 rounded text-xs"
          style={{ background: TK.accent, color: '#fff' }}
        >
          <Play size={10} /> Load
        </button>
        <button
          onClick={() => setMode(mode === 'value' ? 'bind' : 'value')}
          className="flex items-center gap-1 px-1.5 py-0.5 rounded text-xs"
          style={{ background: TK.surface2, color: mode === 'bind' ? TK.accent : TK.dim }}
        >
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
    setLoading(true)
    setError(null)
    try {
      const r = await evaluate(expr, chatState ?? {})
      setResult(r)
    } catch (e) {
      setError(String(e))
      setResult(null)
    } finally {
      setLoading(false)
    }
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
          <button
            onClick={run}
            disabled={loading}
            className="flex items-center gap-1 px-2 py-1 rounded text-xs self-end"
            style={{ background: TK.accent, color: '#fff' }}
          >
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
/*  Main component                                                     */
/* ------------------------------------------------------------------ */

const DEFAULT_TABS: TabDef[] = [
  { id: 'l0log', label: 'L0 Log', closable: false, kind: 'l0log' },
]

let tabCounter = 0
function nextTabId() { return `tab_${++tabCounter}` }

export function DebugConsole({ visible, onClose, chatState, user }: DebugConsoleProps) {
  /* panel state */
  const [pos, setPos] = useState({ x: 80, y: 60 })
  const [size, setSize] = useState({ w: 560, h: 420 })
  const [minimized, setMinimized] = useState(false)
  const [tabs, setTabs] = useState<TabDef[]>(DEFAULT_TABS)
  const [activeTab, setActiveTab] = useState('l0log')
  const [refreshInterval, setRefreshInterval] = useState(3000)

  /* drag state */
  const dragRef = useRef<{ startX: number; startY: number; posX: number; posY: number } | null>(null)
  /* resize state */
  const resizeRef = useRef<{ startX: number; startY: number; w: number; h: number } | null>(null)

  /* drag handlers */
  const onDragStart = (e: ReactMouseEvent) => {
    e.preventDefault()
    dragRef.current = { startX: e.clientX, startY: e.clientY, posX: pos.x, posY: pos.y }
    const onMove = (ev: globalThis.MouseEvent) => {
      if (!dragRef.current) return
      const dx = ev.clientX - dragRef.current.startX
      const dy = ev.clientY - dragRef.current.startY
      setPos({ x: dragRef.current.posX + dx, y: dragRef.current.posY + dy })
    }
    const onUp = () => {
      dragRef.current = null
      document.removeEventListener('mousemove', onMove)
      document.removeEventListener('mouseup', onUp)
    }
    document.addEventListener('mousemove', onMove)
    document.addEventListener('mouseup', onUp)
  }

  /* resize handlers */
  const onResizeStart = (e: ReactMouseEvent) => {
    e.preventDefault()
    e.stopPropagation()
    resizeRef.current = { startX: e.clientX, startY: e.clientY, w: size.w, h: size.h }
    const onMove = (ev: globalThis.MouseEvent) => {
      if (!resizeRef.current) return
      const dw = ev.clientX - resizeRef.current.startX
      const dh = ev.clientY - resizeRef.current.startY
      setSize({
        w: Math.max(320, resizeRef.current.w + dw),
        h: Math.max(200, resizeRef.current.h + dh),
      })
    }
    const onUp = () => {
      resizeRef.current = null
      document.removeEventListener('mousemove', onMove)
      document.removeEventListener('mouseup', onUp)
    }
    document.addEventListener('mousemove', onMove)
    document.addEventListener('mouseup', onUp)
  }

  /* keyboard shortcut: Ctrl+Shift+D to toggle */
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.ctrlKey && e.shiftKey && e.key === 'D') {
        e.preventDefault()
        onClose()
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [onClose])

  /* tab management */
  const addTab = (kind: TabDef['kind'], label: string) => {
    const id = nextTabId()
    setTabs((prev) => [...prev, { id, label, closable: true, kind }])
    setActiveTab(id)
  }

  const closeTab = (id: string) => {
    setTabs((prev) => prev.filter((t) => t.id !== id))
    if (activeTab === id) {
      setActiveTab(tabs[0]?.id ?? 'l0log')
    }
  }

  const currentTab = tabs.find((t) => t.id === activeTab) ?? tabs[0]

  if (!visible) return null

  return (
    <div
      className="fixed z-[9999] flex flex-col rounded-lg overflow-hidden shadow-2xl"
      style={{
        left: pos.x,
        top: pos.y,
        width: minimized ? 280 : size.w,
        height: minimized ? 32 : size.h,
        background: TK.surface,
        border: `1px solid ${TK.border}`,
        fontFamily: '"JetBrains Mono", "Fira Code", "Cascadia Code", monospace',
        fontSize: 12,
        color: TK.text,
      }}
    >
      {/* title bar */}
      <div
        onMouseDown={onDragStart}
        className="flex items-center gap-2 px-2 py-1 cursor-move select-none shrink-0"
        style={{ background: TK.bg, borderBottom: `1px solid ${TK.border}` }}
      >
        <Terminal size={13} style={{ color: TK.accent }} />
        <span className="text-xs font-bold" style={{ color: TK.accent }}>Debug Console</span>
        <span className="text-[10px]" style={{ color: TK.dim }}>Ctrl+Shift+D</span>
        <div className="flex-1" />
        <button
          onClick={() => setMinimized(!minimized)}
          className="p-0.5 rounded hover:opacity-70"
          style={{ color: TK.dim }}
          title="Minimize"
        >
          <Minus size={12} />
        </button>
        <button
          onClick={onClose}
          className="p-0.5 rounded hover:opacity-70"
          style={{ color: TK.err }}
          title="Close"
        >
          <X size={12} />
        </button>
      </div>

      {!minimized && (
        <>
          {/* tab bar */}
          <div
            className="flex items-center gap-0 px-1 shrink-0 overflow-x-auto"
            style={{ background: TK.surface2, borderBottom: `1px solid ${TK.border}` }}
          >
            {tabs.map((t) => (
              <div
                key={t.id}
                className="flex items-center gap-1 px-2 py-1 text-[11px] cursor-pointer shrink-0"
                style={{
                  background: activeTab === t.id ? TK.surface : 'transparent',
                  color: activeTab === t.id ? TK.text : TK.dim,
                  borderBottom: activeTab === t.id ? `2px solid ${TK.accent}` : '2px solid transparent',
                }}
                onClick={() => setActiveTab(t.id)}
              >
                {t.label}
                {t.closable && (
                  <button
                    onClick={(e) => { e.stopPropagation(); closeTab(t.id) }}
                    className="ml-0.5 hover:opacity-70"
                    style={{ color: TK.dim }}
                  >
                    <X size={9} />
                  </button>
                )}
              </div>
            ))}
            {/* add-tab dropdown */}
            <div className="relative group">
              <button
                className="px-1.5 py-1 text-[11px] hover:opacity-70"
                style={{ color: TK.dim }}
                title="Add tab"
              >
                <Plus size={12} />
              </button>
              <div
                className="absolute left-0 top-full hidden group-hover:flex flex-col py-1 rounded shadow-lg z-10"
                style={{ background: TK.bg, border: `1px solid ${TK.border}`, minWidth: 140 }}
              >
                {[
                  { kind: 'inspector' as const, label: 'Object Inspector' },
                  { kind: 'projection' as const, label: 'Projection' },
                  { kind: 'free' as const, label: 'JSONata (Free)' },
                  { kind: 'l0log' as const, label: 'L0 Log' },
                ].map(({ kind, label }) => (
                  <button
                    key={kind}
                    className="text-left px-3 py-1 text-[11px] hover:opacity-80"
                    style={{ color: TK.text }}
                    onClick={() => addTab(kind, label)}
                  >
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
          </div>

          {/* resize handle */}
          <div
            onMouseDown={onResizeStart}
            className="absolute bottom-0 right-0 w-4 h-4 cursor-nwse-resize"
            style={{ opacity: 0.4 }}
          >
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
