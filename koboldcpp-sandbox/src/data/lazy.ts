/**
 * Lazy resolver — compile-time promise pattern.
 *
 * When resolving projections we detect missing references:
 *   field.type = 'ref' | 'path_abs' | 'placeholder'
 *   but target object not in Store (or fields empty).
 *
 * The "virtual object as self-describing query" pattern:
 * walk an object's fields → collect each missing target → batch-query the server
 * via exec /query → ingest response as FieldOps → subscribers re-resolve.
 *
 * Consumer never constructs a query explicitly. The object's own structure IS
 * the query. Missing fields turn into a payload; server responses fill in NULL
 * slots in-place (at the exact atomic paths).
 */
import type { Field, FieldOp, VirtualObject } from './types'
import type { Store } from './store'
import * as api from '@/lib/api'
import { ingestChatState } from './index'

/** A reference that couldn't be resolved locally — becomes a query. */
export interface MissingRef {
  /** Object containing the ref field. */
  requesterId: string
  /** Name of the field holding the ref. */
  fieldName: string
  /** Content that couldn't be resolved (target id / path / placeholder descriptor). */
  target: string
  /** Original field type — hint for resolver. */
  fieldType: string
}

/**
 * Walk an object (or its projection result) collecting references that
 * can't be resolved locally. A field is "missing" when:
 *   - type='ref' and target id is not in store (or has zero fields)
 *   - type='path_abs' and path resolves to nothing
 *   - type='placeholder' (explicit server-fill marker)
 */
export function collectMissingRefs(
  obj: VirtualObject,
  store: Store,
): MissingRef[] {
  const missing: MissingRef[] = []
  for (const [fieldName, field] of obj.fields) {
    const target = referenceTarget(field)
    if (!target) continue
    if (isMissing(target, field.type, store)) {
      missing.push({
        requesterId: obj.id,
        fieldName,
        target,
        fieldType: field.type,
      })
    }
  }
  return missing
}

/** Same walk but over an already-resolved Field[] (e.g. projection output). */
export function collectMissingFromFields(
  fields: Field[],
  requesterId: string,
  store: Store,
): MissingRef[] {
  const missing: MissingRef[] = []
  for (const field of fields) {
    const target = referenceTarget(field)
    if (!target) continue
    if (isMissing(target, field.type, store)) {
      missing.push({
        requesterId,
        fieldName: field.name,
        target,
        fieldType: field.type,
      })
    }
  }
  return missing
}

function referenceTarget(field: Field): string | null {
  if (field.type === 'ref' && typeof field.content === 'string') return field.content
  if (field.type === 'path_abs' && typeof field.content === 'string') return field.content
  if (field.type === 'path_rel' && typeof field.content === 'string') return field.content
  if (field.type === 'placeholder' && typeof field.content === 'string') return field.content
  return null
}

function isMissing(target: string, _fieldType: string, store: Store): boolean {
  const obj = store.get(target)
  return !obj || obj.fields.size === 0
}

// ── Runtime orchestrator ──

/**
 * Resolve all missing refs for an object (or a set of objects) by batching
 * server /query commands via exec.
 *
 * The key design: virtual object + schema tell us exactly what to request.
 * Missing paths → one batch HTTP call → response ingested → subscribers notified.
 *
 * Caller typically wraps with debounce (so multiple resolves during one render
 * collapse into one network round-trip).
 */
export async function resolveMissing(
  missing: MissingRef[],
  user: string,
  store: Store,
): Promise<{ requested: number; resolved: number }> {
  if (missing.length === 0) return { requested: 0, resolved: 0 }

  // De-dupe by target path
  const unique = Array.from(new Set(missing.map((m) => m.target)))
  // Compose batch of /query commands — one per unique target
  const cmds = unique.map((p) => `/query ${p} --depth=1 --limit=50`)

  let resolved = 0
  try {
    const res = (await api.batch(cmds, user)) as { results?: unknown[] }
    const results = res.results ?? []

    // Ingest each returned tree fragment as FieldOps
    for (let i = 0; i < unique.length; i++) {
      const target = unique[i]
      const node = results[i] as QueryResponseNode | undefined
      if (!node) continue
      ingestQueryNode(target, node, store, 'lazy-resolver')
      resolved++
    }
  } catch (e) {
    console.warn('[lazy] resolveMissing failed:', e)
  }

  return { requested: unique.length, resolved }
}

/** Partial shape of /query response node — we only read what we need. */
interface QueryResponseNode {
  path?: string
  name?: string
  meta?: Record<string, unknown>
  data?: Record<string, unknown>
  children?: QueryResponseNode[]
}

/**
 * Ingest a /query response node into Store as FieldOps.
 * Writes to the target's atomic path — fills in the exact missing slot.
 */
function ingestQueryNode(
  target: string,
  node: QueryResponseNode,
  store: Store,
  writer: string,
): void {
  const seqStart = store.lastSeq(writer)
  const seqRef = { current: seqStart }
  const ops: FieldOp[] = []
  const ts = new Date().toISOString()

  // Determine virtual type from meta (default: "unknown")
  const virtualType = (node.meta?.type as string | undefined) ?? 'unknown'
  seqRef.current++
  ops.push({
    seq: seqRef.current,
    writer,
    ts,
    objectId: target,
    fieldName: '_virtualType',
    op: 'set',
    type: 'value',
    content: virtualType,
  })

  // meta fields
  for (const [k, v] of Object.entries(node.meta ?? {})) {
    seqRef.current++
    ops.push({
      seq: seqRef.current,
      writer,
      ts,
      objectId: target,
      fieldName: `_meta.${k}`,
      op: 'set',
      type: 'value',
      content: v,
    })
  }
  // data fields
  for (const [k, v] of Object.entries(node.data ?? {})) {
    seqRef.current++
    ops.push({
      seq: seqRef.current,
      writer,
      ts,
      objectId: target,
      fieldName: `_data.${k}`,
      op: 'set',
      type: 'value',
      content: v,
    })
  }
  // children as refs on the parent — so parent knows its children by id
  if (node.children?.length) {
    for (const child of node.children) {
      const childPath = (child.path as string) ?? `${target}/${child.name ?? ''}`
      seqRef.current++
      ops.push({
        seq: seqRef.current,
        writer,
        ts,
        objectId: target,
        fieldName: `_children.${child.name ?? childPath}`,
        op: 'set',
        type: 'ref',
        content: childPath,
      })
      // Recursively ingest child node
      ingestQueryNode(childPath, child, store, writer)
    }
  }

  store.applyBatch(ops)
}

// ── React convenience ──

/**
 * Utility combining missing detection + resolve into one call.
 * Useful for auto-fetch-on-render patterns.
 */
export async function resolveForObject(
  id: string,
  user: string,
  store: Store,
): Promise<{ requested: number; resolved: number }> {
  const obj = store.get(id)
  if (!obj) {
    // Object itself missing — one-shot query for it
    return resolveMissing(
      [{ requesterId: id, fieldName: '*self*', target: id, fieldType: 'ref' }],
      user,
      store,
    )
  }
  const missing = collectMissingRefs(obj, store)
  return resolveMissing(missing, user, store)
}

// Suppress unused import (kept for future hybrid refresh API)
void ingestChatState
