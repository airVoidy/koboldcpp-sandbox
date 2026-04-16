/**
 * Data Layer entry point — singleton Store + ingest helpers + projections.
 */
import { Store, RAW_PROJECTION, SERIALIZE_PROJECTION } from './store'
import type { FieldOp } from './types'
import type { ChatState, ChatItem } from '@/types/chat'

export * from './types'
export * from './signal'
export { Store } from './store'

// ── Singleton ──

let _store: Store | null = null
export function getStore(): Store {
  if (!_store) {
    _store = new Store()
    _store.registerProjection(RAW_PROJECTION)
    _store.registerProjection(SERIALIZE_PROJECTION)
    // Expose in dev for inspection
    if (typeof window !== 'undefined') {
      ;(window as unknown as { __store: Store }).__store = _store
    }
  }
  return _store
}

// ── Ingest: ChatState → FieldOps ──

/**
 * Convert server ChatState into FieldOps and apply to Store.
 * Uses writer='server' for server-authoritative ingestion.
 * Idempotent via seq per writer.
 */
export function ingestChatState(state: ChatState, writer = 'server'): void {
  const store = getStore()
  const ops: FieldOp[] = []
  const seqRef = { current: store.lastSeq(writer) }

  // Ingest each channel
  for (const ch of state.channels ?? []) {
    ops.push(...itemToOps(ch, 'channel', writer, seqRef))
  }

  // Ingest each message
  for (const msg of state.messages ?? []) {
    ops.push(...itemToOps(msg, 'message', writer, seqRef))
  }

  // Root-level state (active_channel, user, ts)
  if (state.active_channel !== undefined) {
    seqRef.current++
    ops.push({
      seq: seqRef.current,
      writer,
      ts: new Date().toISOString(),
      objectId: 'chat',
      fieldName: 'active_channel',
      op: 'set',
      type: 'value',
      content: state.active_channel,
    })
  }

  store.applyBatch(ops)

  // Instantiate RuntimeObjects for all VirtualObjects (virtual adapter by default)
  // Runtime layer is a separate module; defer to avoid circular import.
  void import('@/runtime').then(({ instantiateAllFromStore }) => {
    instantiateAllFromStore()
  })
}

function itemToOps(
  item: ChatItem,
  virtualType: string,
  writer: string,
  seqRef: { current: number },
): FieldOp[] {
  const id = item.path || item.name
  const ops: FieldOp[] = []
  const ts = new Date().toISOString()

  // Set virtualType first
  seqRef.current++
  ops.push({
    seq: seqRef.current,
    writer,
    ts,
    objectId: id,
    fieldName: '_virtualType',
    op: 'set',
    type: 'value',
    content: virtualType,
  })

  // Meta fields
  for (const [key, value] of Object.entries(item.meta ?? {})) {
    seqRef.current++
    ops.push({
      seq: seqRef.current,
      writer,
      ts,
      objectId: id,
      fieldName: `_meta.${key}`,
      op: 'set',
      type: 'value',
      content: value,
    })
  }

  // Data fields
  for (const [key, value] of Object.entries(item.data ?? {})) {
    seqRef.current++
    ops.push({
      seq: seqRef.current,
      writer,
      ts,
      objectId: id,
      fieldName: `_data.${key}`,
      op: 'set',
      type: 'value',
      content: value,
    })
  }

  return ops
}
