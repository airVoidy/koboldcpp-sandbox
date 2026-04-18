/**
 * Field store hook — exposes chat state as flat field store.
 * L1 layer: canonical fields, dot-path addressable.
 */
import { useMemo } from 'react'
import { useChat } from './useChat'
import type { FieldEntry } from '@/types/runtime'
import { toFieldStore, fromFieldStore, patchFieldStore } from '@/types/runtime'
import * as api from '@/lib/api'

export function useFieldStore() {
  const chat = useChat()

  const messageStore = useMemo(() => {
    const store: Record<string, FieldEntry> = {}
    for (const msg of chat.messages) {
      const prefix = msg.name
      if (msg.meta) {
        for (const [k, v] of Object.entries(msg.meta)) {
          const path = `${prefix}._meta.${k}`
          store[path] = [String(path.length), path, v]
        }
      }
      if (msg.data) {
        for (const [k, v] of Object.entries(msg.data)) {
          const path = `${prefix}._data.${k}`
          store[path] = [String(path.length), path, v]
        }
      }
    }
    return store
  }, [chat.messages])

  const channelStore = useMemo(() => {
    const store: Record<string, FieldEntry> = {}
    for (const ch of chat.channels) {
      const name = ch.meta?.name ?? ch.name
      store[`channels.${name}`] = [name, `channels.${name}`, ch.meta]
    }
    return store
  }, [chat.channels])

  /** Fetch template aggregation via exec */
  const fetchProjection = async (template: string, scope?: string) => {
    const cmd = scope ? `/mproject ${template} --scope=${scope}` : `/mproject ${template}`
    return api.exec(cmd, 'anon')
  }

  return {
    ...chat,
    messageStore,
    channelStore,
    fetchProjection,
    toFieldStore,
    fromFieldStore,
    patchFieldStore,
  }
}
