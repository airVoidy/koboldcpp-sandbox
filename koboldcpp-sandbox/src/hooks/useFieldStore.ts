/**
 * Field store hook — exposes chat state as flat field store.
 * Projection over useChat, not a replacement.
 *
 * L1 layer: canonical fields, dot-path addressable.
 */
import { useMemo } from 'react'
import { useChat } from './useChat'
import type { FieldEntry, Projection, TemplateAggregation } from '@/types/runtime'
import { toFieldStore, fromFieldStore, patchFieldStore } from '@/types/runtime'
import * as api from '@/lib/api'

export function useFieldStore() {
  const chat = useChat()

  /** Current messages as flat field store */
  const messageStore = useMemo(() => {
    const store: Record<string, FieldEntry> = {}
    for (const msg of chat.messages) {
      const prefix = msg.name
      // Meta fields
      if (msg.meta) {
        for (const [k, v] of Object.entries(msg.meta)) {
          const path = `${prefix}._meta.${k}`
          store[path] = [String(path.length), path, v]
        }
      }
      // Data fields
      if (msg.data) {
        for (const [k, v] of Object.entries(msg.data)) {
          const path = `${prefix}._data.${k}`
          store[path] = [String(path.length), path, v]
        }
      }
    }
    return store
  }, [chat.messages])

  /** Channel list as flat field store */
  const channelStore = useMemo(() => {
    const store: Record<string, FieldEntry> = {}
    for (const ch of chat.channels) {
      const name = ch.meta?.name ?? ch.name
      store[`channels.${name}`] = [name, `channels.${name}`, ch.meta]
    }
    return store
  }, [chat.channels])

  /** Fetch server-side template aggregation */
  const fetchProjection = async (template: string, scope?: string): Promise<TemplateAggregation> => {
    return api.getProjection(template, scope) as Promise<TemplateAggregation>
  }

  return {
    ...chat,
    messageStore,
    channelStore,
    fetchProjection,
    // Re-export utilities
    toFieldStore,
    fromFieldStore,
    patchFieldStore,
  }
}
