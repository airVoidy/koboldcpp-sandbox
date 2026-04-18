/**
 * RuntimeAtomicDemo — immediate-projection invariant on the real runtime.
 *
 * Reach via URL hash: `#runtime-demo` (App.tsx routes to this).
 *
 * Three live containers + a side panel against real plumbing:
 *
 * 1. BashTerminal (real, just-bash + InMemoryFs) — already 100% local-first.
 *    Stdout appears instantly regardless of any "server" simulation. The
 *    middlelayer.exec record is audit-only (see BashTerminal.tsx:90-98).
 *    THIS is what immediate-projection looks like in production.
 *
 * 2. Two Lexical containers (one editor, one viewer) over the SAME Store object.
 *    Editor's `registerUpdateListener` emits FieldOps. Viewer rebuilds its
 *    EditorState from Store content on every store.subscribe bump. No
 *    client-server route in the loop — the projection IS Lexical state, derived
 *    in real time. Mode toggle wraps editor's emit in either local-first
 *    (apply now, ack later) or server-gated (ack first, then apply) — only the
 *    second freezes the projection visibly.
 *
 * 3. Side panel: live Store inspector + ack timeline + middlelayer.getCallLog()
 *    for the bash audit entries.
 */
import { useEffect, useRef, useState, useCallback } from 'react'
import {
  createEditor,
  $getRoot,
  $createParagraphNode,
  $createTextNode,
  type LexicalEditor,
} from 'lexical'
import { HeadingNode, QuoteNode, registerRichText } from '@lexical/rich-text'
import { registerHistory, createEmptyHistoryState } from '@lexical/history'
import { mergeRegister } from '@lexical/utils'
import { BashTerminal } from '@/components/BashTerminal'
import { getStore } from '@/data'
import { getMiddlelayer } from '@/runtime/middlelayer'

const DEMO_OBJECT_ID = 'demo:doc'
const DEMO_FIELD = 'content'
const WRITER = 'demo-text'

type Mode = 'local' | 'server'

interface PendingAck {
  id: string
  text: string
  startedAt: number
  status: 'pending' | 'confirmed' | 'failed'
  ackMs?: number
  error?: string
}

// ── Lexical container — same primitive in editor + viewer roles ──────────

interface LexicalContainerProps {
  /** External text source (used in viewer mode to drive content). */
  externalText?: string
  /** Called on every editor update with the new text content. */
  onTextChange?: (text: string) => void
  /** If true, container is read-only and reflects externalText only. */
  readOnly?: boolean
  /** Initial text on first mount (editor mode only). */
  seed?: string
}

function LexicalContainer({
  externalText,
  onTextChange,
  readOnly = false,
  seed = '',
}: LexicalContainerProps) {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const editorRef = useRef<LexicalEditor | null>(null)
  const lastAppliedExternalRef = useRef<string>('')

  // onTextChange ref so the update listener always sees the latest closure
  const onTextChangeRef = useRef(onTextChange)
  onTextChangeRef.current = onTextChange

  useEffect(() => {
    if (!containerRef.current) return

    const editor = createEditor({
      namespace: 'runtime-demo-' + (readOnly ? 'viewer' : 'editor'),
      onError: (e) => console.error('lexical error:', e),
      nodes: [HeadingNode, QuoteNode],
      editable: !readOnly,
      theme: {
        paragraph: 'lex-p',
        heading: { h1: 'lex-h1', h2: 'lex-h2' },
        quote: 'lex-quote',
      },
    })
    editor.setRootElement(containerRef.current)

    const cleanups: Array<() => void> = []

    if (!readOnly) {
      cleanups.push(
        registerRichText(editor),
        registerHistory(editor, createEmptyHistoryState(), 300),
      )
      cleanups.push(
        editor.registerUpdateListener(({ editorState }) => {
          editorState.read(() => {
            const text = $getRoot().getTextContent()
            onTextChangeRef.current?.(text)
          })
        }),
      )
    }

    // Seed initial content
    const initial = readOnly ? externalText ?? '' : seed
    if (initial) {
      editor.update(() => {
        const root = $getRoot()
        root.clear()
        const p = $createParagraphNode()
        p.append($createTextNode(initial))
        root.append(p)
      })
      lastAppliedExternalRef.current = initial
    }

    editorRef.current = editor

    return () => {
      mergeRegister(...cleanups)()
      editor.setRootElement(null)
      editorRef.current = null
    }
    // Only depends on readOnly — recreate editor only on role change
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [readOnly])

  // Viewer mode: when externalText changes, rebuild Lexical state
  useEffect(() => {
    if (!readOnly) return
    const editor = editorRef.current
    if (!editor) return
    const next = externalText ?? ''
    if (next === lastAppliedExternalRef.current) return
    lastAppliedExternalRef.current = next
    editor.update(() => {
      const root = $getRoot()
      root.clear()
      if (next) {
        const p = $createParagraphNode()
        p.append($createTextNode(next))
        root.append(p)
      }
    })
  }, [externalText, readOnly])

  return (
    <div
      ref={containerRef}
      contentEditable={!readOnly}
      suppressContentEditableWarning
      spellCheck={false}
      className="flex-1 p-4 outline-none overflow-auto whitespace-pre-wrap text-sm leading-relaxed"
      style={{ fontFamily: '"JetBrains Mono", Menlo, monospace' }}
    />
  )
}

// ── Main demo ────────────────────────────────────────────────────────────

export function RuntimeAtomicDemo() {
  const store = getStore()
  const middlelayer = getMiddlelayer()

  const [mode, setMode] = useState<Mode>('local')
  const [latencyMs, setLatencyMs] = useState(600)
  const [errorRate, setErrorRate] = useState(0)
  const [storeVersion, setStoreVersion] = useState(() => store.version(DEMO_OBJECT_ID))
  const [callLogVersion, setCallLogVersion] = useState(0)
  const [acks, setAcks] = useState<PendingAck[]>([])

  // Refs so async closures see latest control values
  const modeRef = useRef(mode)
  const latencyRef = useRef(latencyMs)
  const errorRef = useRef(errorRate)
  modeRef.current = mode
  latencyRef.current = latencyMs
  errorRef.current = errorRate

  // Subscribe to Store changes on the demo object — drives the viewer Lexical
  useEffect(() => {
    return store.subscribe(DEMO_OBJECT_ID, () => {
      setStoreVersion(store.version(DEMO_OBJECT_ID))
    })
  }, [store])

  // Subscribe to middlelayer afterHook to bump call-log render
  useEffect(() => {
    return middlelayer.onAfterExec(() => {
      setCallLogVersion((v) => v + 1)
    })
  }, [middlelayer])

  function applyToStore(text: string) {
    const op = store.makeOp(WRITER, {
      objectId: DEMO_OBJECT_ID,
      fieldName: DEMO_FIELD,
      op: 'set',
      type: 'value',
      content: text,
    })
    store.applyBatch([op])
  }

  function fakeAck(): Promise<{ ackMs: number }> {
    return new Promise((resolve, reject) => {
      const startedAt = performance.now()
      setTimeout(() => {
        if (Math.random() * 100 < errorRef.current) {
          reject(new Error('simulated server failure'))
        } else {
          resolve({ ackMs: performance.now() - startedAt })
        }
      }, latencyRef.current)
    })
  }

  // Editor → Store with mode-based gating
  const handleEditorTextChange = useCallback(
    (text: string) => {
      const ackId = 'ack_' + Math.random().toString(36).slice(2, 8)
      const startedAt = Date.now()
      const preview = text.slice(0, 40)

      if (modeRef.current === 'local') {
        // Local-first: apply NOW, ack later. Viewer reflects instantly.
        applyToStore(text)
        setAcks((prev) =>
          [...prev, { id: ackId, text: preview, startedAt, status: 'pending' as const }].slice(-30),
        )
        fakeAck().then(
          ({ ackMs }) => {
            setAcks((prev) =>
              prev.map((a) =>
                a.id === ackId ? { ...a, status: 'confirmed' as const, ackMs } : a,
              ),
            )
          },
          (err: Error) => {
            setAcks((prev) =>
              prev.map((a) =>
                a.id === ackId ? { ...a, status: 'failed' as const, error: err.message } : a,
              ),
            )
          },
        )
      } else {
        // Server-gated: BLOCK on ack before applying. Viewer freezes for latencyMs.
        setAcks((prev) =>
          [...prev, { id: ackId, text: preview, startedAt, status: 'pending' as const }].slice(-30),
        )
        fakeAck().then(
          ({ ackMs }) => {
            applyToStore(text)
            setAcks((prev) =>
              prev.map((a) =>
                a.id === ackId ? { ...a, status: 'confirmed' as const, ackMs } : a,
              ),
            )
          },
          (err: Error) => {
            setAcks((prev) =>
              prev.map((a) =>
                a.id === ackId ? { ...a, status: 'failed' as const, error: err.message } : a,
              ),
            )
          },
        )
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [],
  )

  function reset() {
    setAcks([])
    // Note: not clearing Store — it's canonical truth, persists across resets
  }

  // ── Read live state for render ──
  const docObject = store.get(DEMO_OBJECT_ID)
  const storeContent = (docObject?.fields.get(DEMO_FIELD)?.content as string | undefined) ?? ''
  const callLog = middlelayer.getCallLog()
  void storeVersion // re-render trigger
  void callLogVersion // re-render trigger

  const pendingCount = acks.filter((a) => a.status === 'pending').length
  const failedCount = acks.filter((a) => a.status === 'failed').length

  return (
    <div className="flex flex-col h-screen bg-[var(--bg)] text-[var(--text)]">
      <header className="flex items-center gap-4 px-4 py-2 border-b border-[var(--border)] flex-wrap">
        <span className="font-bold uppercase tracking-wider text-[var(--accent)] text-sm">
          runtime-atomic · dual-Lexical projection
        </span>

        <div className="flex items-center gap-1 bg-[var(--surface-2)] border border-[var(--border)] rounded p-0.5">
          <button
            onClick={() => setMode('local')}
            className={`px-3 py-1 text-xs rounded ${
              mode === 'local'
                ? 'bg-[var(--accent)] text-black font-bold'
                : 'text-[var(--text-dim)] hover:text-[var(--text)]'
            }`}
          >
            local-first
          </button>
          <button
            onClick={() => setMode('server')}
            className={`px-3 py-1 text-xs rounded ${
              mode === 'server'
                ? 'bg-[var(--accent)] text-black font-bold'
                : 'text-[var(--text-dim)] hover:text-[var(--text)]'
            }`}
          >
            server-gated
          </button>
        </div>

        <label className="flex items-center gap-2 text-xs text-[var(--text-dim)]">
          latency
          <input
            type="range"
            min={0}
            max={2000}
            step={50}
            value={latencyMs}
            onChange={(e) => setLatencyMs(Number(e.target.value))}
            className="w-32"
          />
          <span className="text-[var(--text)] w-14">{latencyMs}ms</span>
        </label>

        <label className="flex items-center gap-2 text-xs text-[var(--text-dim)]">
          error %
          <input
            type="range"
            min={0}
            max={100}
            step={5}
            value={errorRate}
            onChange={(e) => setErrorRate(Number(e.target.value))}
            className="w-24"
          />
          <span className="text-[var(--text)] w-10">{errorRate}%</span>
        </label>

        <button
          onClick={reset}
          className="px-3 py-1 text-xs bg-[var(--surface-2)] border border-[var(--border)] rounded hover:border-[var(--accent)]"
        >
          reset acks
        </button>

        <span className="text-xs text-[var(--text-dim)] ml-auto max-w-md text-right leading-tight">
          editor + viewer = same Lexical primitive over same Store object.<br />
          local-first: viewer mirrors instantly · server-gated: viewer waits for ack.
        </span>
      </header>

      <main className="flex-1 grid grid-cols-[1fr_1fr_1fr_360px] gap-px bg-[var(--border)] min-h-0">
        {/* ── BashTerminal ── */}
        <div className="flex flex-col bg-[var(--bg)] min-h-0">
          <div className="px-3 py-2 text-xs uppercase tracking-wider text-[var(--text-dim)] bg-[var(--surface)] border-b border-[var(--border)] flex justify-between items-center">
            <span>bash · just-bash</span>
            <span className="text-[var(--green)] normal-case tracking-normal text-[10px]">
              real, always local
            </span>
          </div>
          <div className="flex-1 min-h-0">
            <BashTerminal requester="runtime-demo" recordToMiddlelayer={true} />
          </div>
        </div>

        {/* ── Lexical EDITOR ── */}
        <div className="flex flex-col bg-[var(--bg)] min-h-0">
          <div className="px-3 py-2 text-xs uppercase tracking-wider text-[var(--text-dim)] bg-[var(--surface)] border-b border-[var(--border)] flex justify-between items-center">
            <span>lexical · editor (source)</span>
            <span
              className={`normal-case tracking-normal text-[10px] ${
                mode === 'local' ? 'text-[var(--green)]' : 'text-[var(--yellow)]'
              }`}
            >
              mode: {mode}
            </span>
          </div>
          <LexicalContainer
            seed="Type here. Editor → FieldOp → Store → Viewer (also Lexical). Same primitive on both ends. Switch to server-gated mode and watch the viewer freeze."
            onTextChange={handleEditorTextChange}
          />
        </div>

        {/* ── Lexical VIEWER (projection) ── */}
        <div className="flex flex-col bg-[var(--bg)] min-h-0">
          <div className="px-3 py-2 text-xs uppercase tracking-wider text-[var(--text-dim)] bg-[var(--surface)] border-b border-[var(--border)] flex justify-between items-center">
            <span>lexical · viewer (Store projection)</span>
            <span className="normal-case tracking-normal text-[10px] text-[var(--text-dim)]">
              v{storeVersion} · {storeContent.length}ch
            </span>
          </div>
          <LexicalContainer externalText={storeContent} readOnly />
        </div>

        {/* ── Side panel ── */}
        <div className="flex flex-col bg-[var(--bg)] min-h-0 overflow-hidden">
          <div className="px-3 py-2 border-b border-[var(--border)] bg-[var(--surface)]">
            <div className="text-xs uppercase tracking-wider text-[var(--text-dim)] mb-2">
              text · stats
            </div>
            <div className="grid grid-cols-2 gap-x-3 gap-y-1 text-xs">
              <Stat label="acks total" value={acks.length} />
              <Stat label="pending" value={pendingCount} color="var(--yellow)" />
              <Stat label="failed" value={failedCount} color="var(--red)" />
              <Stat label="store v" value={storeVersion} color="var(--green)" />
            </div>
          </div>

          <div className="flex-1 min-h-0 flex flex-col border-b border-[var(--border)]">
            <div className="px-3 py-2 text-xs uppercase tracking-wider text-[var(--text-dim)] bg-[var(--surface)] border-b border-[var(--border)]">
              editor edits · ack timeline
            </div>
            <div className="flex-1 overflow-auto p-2 space-y-1 text-xs">
              {acks.length === 0 && (
                <div className="text-[var(--text-dim)] italic text-center py-4">
                  type in the editor →
                </div>
              )}
              {[...acks].reverse().map((a) => (
                <div
                  key={a.id}
                  className="px-2 py-1 rounded border-l-2 bg-[var(--surface-2)] flex justify-between items-start gap-2"
                  style={{
                    borderColor:
                      a.status === 'confirmed'
                        ? 'var(--green)'
                        : a.status === 'failed'
                          ? 'var(--red)'
                          : 'var(--yellow)',
                  }}
                >
                  <span className="font-mono text-[var(--text-dim)] truncate flex-1">
                    "{a.text || '(empty)'}"
                  </span>
                  <span
                    className="text-[10px] uppercase tracking-wider whitespace-nowrap"
                    style={{
                      color:
                        a.status === 'confirmed'
                          ? 'var(--green)'
                          : a.status === 'failed'
                            ? 'var(--red)'
                            : 'var(--yellow)',
                    }}
                  >
                    {a.status === 'confirmed' && a.ackMs !== undefined
                      ? `+${a.ackMs.toFixed(0)}ms`
                      : a.status}
                  </span>
                </div>
              ))}
            </div>
          </div>

          <div className="flex-1 min-h-0 flex flex-col">
            <div className="px-3 py-2 text-xs uppercase tracking-wider text-[var(--text-dim)] bg-[var(--surface)] border-b border-[var(--border)]">
              middlelayer.callLog · bash audit
            </div>
            <div className="flex-1 overflow-auto p-2 space-y-1 text-xs">
              {callLog.length === 0 && (
                <div className="text-[var(--text-dim)] italic text-center py-4">
                  run a bash cmd in the left pane →
                </div>
              )}
              {[...callLog]
                .reverse()
                .slice(0, 20)
                .map((entry, i) => (
                  <div
                    key={i}
                    className="px-2 py-1 rounded border-l-2 bg-[var(--surface-2)]"
                    style={{
                      borderColor: entry.result.ok ? 'var(--accent)' : 'var(--red)',
                    }}
                  >
                    <div className="font-mono text-[var(--text)] truncate">
                      {entry.ctx.cmd.startsWith('__shell ')
                        ? '$ ' +
                          (() => {
                            try {
                              return JSON.parse(entry.ctx.cmd.slice(8)).cmd
                            } catch {
                              return entry.ctx.cmd
                            }
                          })()
                        : entry.ctx.cmd}
                    </div>
                    <div className="text-[10px] text-[var(--text-dim)] flex justify-between">
                      <span>{entry.ctx.requester}</span>
                      <span>{entry.result.durationMs.toFixed(0)}ms</span>
                    </div>
                  </div>
                ))}
            </div>
          </div>
        </div>
      </main>
    </div>
  )
}

function Stat({
  label,
  value,
  color,
}: {
  label: string
  value: number | string
  color?: string
}) {
  return (
    <div className="flex justify-between">
      <span className="text-[var(--text-dim)]">{label}</span>
      <span style={{ color: color ?? 'var(--text)', fontWeight: 700 }}>{value}</span>
    </div>
  )
}
