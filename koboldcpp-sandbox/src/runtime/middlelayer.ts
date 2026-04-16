/**
 * Middlelayer — the balancer/local-sandbox between caller and server exec.
 *
 * Every exec command routes through here. Middlelayer:
 * 1. Captures prev_state snapshot for affected fields (read-before-write)
 * 2. Sends cmd to server via /pchat/exec (one response = one diff)
 * 3. Applies returned FieldOp diff to Store
 * 4. ALSO writes shadow metadata fields _exec.<callId>.{cmd,requester,prev,ts}
 *    alongside each mutated field — "patch-with-provenance" pattern
 * 5. Resolves new_state projections relative to prev_state
 * 6. Returns ExecResult {diff, stdout, stderr, meta} to caller
 *
 * The same path is used for both the state-of-truth value and its shadow exec
 * history. Projections separate them:
 *   - `current_value`: shows only `.content`
 *   - `exec_history`: walks `.content._exec.*` entries
 *
 * Hooks enable additional transformations:
 *   - onBeforeExec: mutate/validate/batch the cmd before send
 *   - onAfterExec: post-process result, add to audit log, trigger reactions
 *
 * The middlelayer is what bash-tool's onBefore/onAfterBashCall hook would
 * attach to — making our exec pipeline interchangeable with bash-tool shells.
 */
import type { FieldOp } from '@/data/types'
import type { Store } from '@/data/store'
import * as api from '@/lib/api'

/** Unique id for an exec call — used as correlation id in shadow metadata. */
let _callCounter = 0
function nextCallId(requester: string): string {
  return `${requester}_${Date.now()}_${++_callCounter}`
}

export interface ExecContext {
  /** Correlation id — generated if not provided. */
  callId?: string
  /** The cmd string to execute. */
  cmd: string
  /** Who issued (user id, agent id, workflow id). */
  requester: string
  /** User for server audit. Usually same as requester. */
  user?: string
  /** ISO ts — generated if not provided. */
  ts?: string
  /** Optional scope hint (defaults to 'CMD'). */
  scope?: string
  /** Fields we expect to be affected — used for prev_state snapshot. */
  expectedTargets?: Array<{ objectId: string; fieldName: string }>
}

export interface ExecResult {
  ok: boolean
  /** Correlation id to link response back to call. */
  callId: string
  /** FieldOp diff applied to Store. May be empty for read-only cmds. */
  diff: FieldOp[]
  /** Raw stdout / stderr if server provided. */
  stdout?: string
  stderr?: string
  /** Error message if ok=false. */
  error?: string
  /** Timing. */
  durationMs: number
  /** Snapshot of fields BEFORE the change, keyed by "objectId#fieldName". */
  prevState: Record<string, unknown>
  /** Resolved NEW values for the same keys (after diff applied). */
  newState: Record<string, unknown>
}

export type BeforeHook = (ctx: ExecContext) => ExecContext | Promise<ExecContext> | void
export type AfterHook = (
  ctx: ExecContext,
  result: ExecResult,
) => ExecResult | Promise<ExecResult> | void

export class Middlelayer {
  private store: Store
  private beforeHooks: BeforeHook[] = []
  private afterHooks: AfterHook[] = []
  /** Track all execs for audit / history projections. */
  private callLog: Array<{ ctx: ExecContext; result: ExecResult }> = []

  constructor(store: Store) {
    this.store = store
  }

  /** Register a pre-exec hook (e.g. batching, validation, logging). */
  onBeforeExec(hook: BeforeHook): () => void {
    this.beforeHooks.push(hook)
    return () => {
      const i = this.beforeHooks.indexOf(hook)
      if (i >= 0) this.beforeHooks.splice(i, 1)
    }
  }

  /** Register a post-exec hook (e.g. result transform, telemetry, cache). */
  onAfterExec(hook: AfterHook): () => void {
    this.afterHooks.push(hook)
    return () => {
      const i = this.afterHooks.indexOf(hook)
      if (i >= 0) this.afterHooks.splice(i, 1)
    }
  }

  /** Get history of calls — for audit UIs / replay / debug. */
  getCallLog(): ReadonlyArray<{ ctx: ExecContext; result: ExecResult }> {
    return this.callLog
  }

  /**
   * Execute a cmd through the middlelayer.
   * The main entry point — replaces direct api.exec() calls where provenance matters.
   */
  async exec(rawCtx: ExecContext): Promise<ExecResult> {
    const t0 = performance.now()

    // Fill defaults
    let ctx: ExecContext = {
      ...rawCtx,
      callId: rawCtx.callId ?? nextCallId(rawCtx.requester),
      ts: rawCtx.ts ?? new Date().toISOString(),
      user: rawCtx.user ?? rawCtx.requester,
      scope: rawCtx.scope ?? 'CMD',
    }

    // Run before hooks (may mutate ctx)
    for (const h of this.beforeHooks) {
      const next = await h(ctx)
      if (next) ctx = next
    }

    // Snapshot prev state for expected targets (before server call)
    const prevState = this.snapshotTargets(ctx.expectedTargets ?? [])

    // Send to server
    let serverResult: unknown
    let errorMessage: string | undefined
    try {
      serverResult = await api.exec(ctx.cmd, ctx.user!, ctx.scope)
    } catch (e) {
      errorMessage = e instanceof Error ? e.message : String(e)
    }

    // Extract diff (server may send diff format or legacy full result)
    const diff = this.extractDiff(serverResult, ctx)

    // Apply diff to Store (state-of-truth update)
    if (diff.length > 0) {
      this.store.applyBatch(diff)
    }

    // Write shadow metadata fields alongside each mutated path
    this.writeExecShadow(diff, ctx)

    // Snapshot new state (after applying)
    const newState = this.snapshotTargets(
      diff.map((op) => ({ objectId: op.objectId, fieldName: op.fieldName })),
    )

    // Build result
    let result: ExecResult = {
      ok: !errorMessage && !(serverResult as { error?: string })?.error,
      callId: ctx.callId!,
      diff,
      stdout:
        (serverResult as { stdout?: string })?.stdout ??
        (typeof serverResult === 'string' ? serverResult : undefined),
      stderr: (serverResult as { stderr?: string })?.stderr,
      error:
        errorMessage ??
        (typeof (serverResult as { error?: unknown })?.error === 'string'
          ? ((serverResult as { error: string }).error)
          : undefined),
      durationMs: performance.now() - t0,
      prevState,
      newState,
    }

    // Run after hooks (may transform result)
    for (const h of this.afterHooks) {
      const next = await h(ctx, result)
      if (next) result = next
    }

    // Record in call log
    this.callLog.push({ ctx, result })
    if (this.callLog.length > 1000) this.callLog.shift() // bounded

    return result
  }

  // ── Internals ──

  /** Capture current values for the given targets (before or after apply). */
  private snapshotTargets(
    targets: Array<{ objectId: string; fieldName: string }>,
  ): Record<string, unknown> {
    const snap: Record<string, unknown> = {}
    for (const t of targets) {
      const obj = this.store.get(t.objectId)
      const field = obj?.fields.get(t.fieldName)
      snap[`${t.objectId}#${t.fieldName}`] = field?.content
    }
    return snap
  }

  /**
   * Translate server response → FieldOp[] diff.
   * Server may send:
   *   1. Our native format: { diff: FieldOp[] }       — preferred
   *   2. ChatState-style blob: { channels, messages } — legacy, skip for now
   *   3. Raw query tree: { path, meta, data }         — ingest via lazy resolver
   * For (2)+(3), return empty diff; caller can fall back to lazy resolver.
   */
  private extractDiff(serverResult: unknown, _ctx: ExecContext): FieldOp[] {
    if (!serverResult || typeof serverResult !== 'object') return []
    const r = serverResult as { diff?: FieldOp[] }
    if (Array.isArray(r.diff)) {
      // Validate basic shape
      return r.diff.filter(
        (o): o is FieldOp =>
          typeof o === 'object' &&
          o !== null &&
          typeof (o as FieldOp).objectId === 'string' &&
          typeof (o as FieldOp).fieldName === 'string' &&
          typeof (o as FieldOp).seq === 'number' &&
          typeof (o as FieldOp).writer === 'string',
      )
    }
    return []
  }

  /**
   * Write shadow _exec.* metadata fields alongside each mutated path.
   * Pattern: <fieldName>._exec.<callId>.{cmd, requester, prev, ts}
   *
   * This is the "additional fields in projections" trick: they don't appear in
   * the default `current_value` projection, but are queryable via
   * `exec_history` / `diff_since` projections.
   */
  private writeExecShadow(diff: FieldOp[], ctx: ExecContext): void {
    if (diff.length === 0) return
    const writer = 'middlelayer'
    const ops: FieldOp[] = []
    for (const op of diff) {
      const prev = this.store.get(op.objectId)?.fields.get(op.fieldName)?.content
      const basePath = `${op.fieldName}._exec.${ctx.callId}`
      const entries: Array<[string, unknown]> = [
        ['cmd', ctx.cmd],
        ['requester', ctx.requester],
        ['ts', ctx.ts],
        ['prev', prev ?? null],
      ]
      for (const [k, v] of entries) {
        ops.push(
          this.store.makeOp(writer, {
            objectId: op.objectId,
            fieldName: `${basePath}.${k}`,
            op: 'set',
            type: 'value',
            content: v,
          }),
        )
      }
    }
    this.store.applyBatch(ops)
  }
}

// ── Singleton ──

import { getStore } from '@/data'

let _middlelayer: Middlelayer | null = null
export function getMiddlelayer(): Middlelayer {
  if (!_middlelayer) {
    _middlelayer = new Middlelayer(getStore())
    if (typeof window !== 'undefined') {
      ;(window as unknown as { __middlelayer: Middlelayer }).__middlelayer = _middlelayer
    }
  }
  return _middlelayer
}
