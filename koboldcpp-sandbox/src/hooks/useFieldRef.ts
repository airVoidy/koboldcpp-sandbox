/**
 * useFieldRef — reactive reference to a field in the runtime store.
 *
 * Returns { hash, path, value, display } where display = current facet.
 * Switching display re-renders with different facet.
 * Source changes → all refs with same path re-render.
 *
 * This is the client-side equivalent of server field projections:
 * field[field.display] — one object, three facets.
 */
import { useMemo, useState, createContext, useContext, createElement, type ReactNode } from 'react'
import type { ChatState } from '@/types/chat'
import { getByPath } from '@/types/runtime'

export type DisplayFacet = 'value' | 'path' | 'hash'

export interface FieldRef {
  hash: string
  path: string
  value: unknown
  display: DisplayFacet
  /** Resolved display value: self[self.display] */
  resolved: unknown
}

/** Context for container-level display switching */
const DisplayContext = createContext<DisplayFacet>('value')

export function DisplayProvider({ facet, children }: { facet: DisplayFacet; children: ReactNode }) {
  return createElement(DisplayContext.Provider, { value: facet }, children)
}

/** Simple hash for field identity */
function fieldHash(path: string, value: unknown): string {
  const str = `${path}:${JSON.stringify(value)}`
  let h = 0
  for (let i = 0; i < str.length; i++) {
    h = ((h << 5) - h + str.charCodeAt(i)) | 0
  }
  return h.toString(36)
}

/**
 * Get a reactive field reference from chat state.
 * @param state - Current chat state (source of truth)
 * @param path - Dot-path to field (e.g. "msg_1._data.content")
 * @param overrideDisplay - Override container-level display facet
 */
export function useFieldRef(
  state: ChatState | null,
  path: string,
  overrideDisplay?: DisplayFacet,
): FieldRef {
  const containerDisplay = useContext(DisplayContext)
  const display = overrideDisplay ?? containerDisplay

  return useMemo(() => {
    if (!state) {
      return { hash: '', path, value: null, display, resolved: null }
    }

    // Resolve value from state by path
    // Path format: "msg_1._data.content" or "channels.general._meta.name"
    const parts = path.split('.')
    let value: unknown = null

    // Try messages first
    if (parts[0]?.startsWith('msg_')) {
      const msg = state.messages.find(m => m.name === parts[0])
      if (msg) {
        const subPath = parts.slice(1).join('.')
        if (subPath.startsWith('_meta.')) {
          value = getByPath(msg.meta, subPath.slice(6))
        } else if (subPath.startsWith('_data.')) {
          value = getByPath(msg.data, subPath.slice(6))
        } else {
          value = getByPath(msg.data, subPath) ?? getByPath(msg.meta, subPath)
        }
      }
    }

    // Try channels
    if (value === null && parts[0] === 'channels') {
      const ch = state.channels.find(c => (c.meta?.name ?? c.name) === parts[1])
      if (ch) {
        const subPath = parts.slice(2).join('.')
        if (!subPath) value = ch
        else if (subPath.startsWith('_meta.')) value = getByPath(ch.meta, subPath.slice(6))
        else if (subPath.startsWith('_data.')) value = getByPath(ch.data, subPath.slice(6))
        else value = getByPath(ch.data, subPath) ?? getByPath(ch.meta, subPath)
      }
    }

    // Generic: try getByPath on whole state
    if (value === null) {
      value = getByPath(state as unknown as Record<string, unknown>, path)
    }

    const hash = fieldHash(path, value)
    const ref: FieldRef = { hash, path, value, display, resolved: null }

    // self[self.display]
    switch (display) {
      case 'value': ref.resolved = value; break
      case 'path': ref.resolved = path; break
      case 'hash': ref.resolved = hash; break
    }

    return ref
  }, [state, path, display])
}

/**
 * useDisplayFacet — hook to toggle container-level display.
 */
export function useDisplayFacet(initial: DisplayFacet = 'value') {
  const [facet, setFacet] = useState<DisplayFacet>(initial)
  const cycle = () => {
    setFacet(f => f === 'value' ? 'path' : f === 'path' ? 'hash' : 'value')
  }
  return { facet, setFacet, cycle }
}
