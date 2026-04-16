/**
 * React bindings for the Data Layer Store.
 *
 * - useStore()           — singleton access (doesn't re-render on its own)
 * - useVirtualObject(id) — subscribes to per-object version signal, re-renders on change
 * - useProjection(id, name) — resolves projection, re-renders on version bump
 * - useAllObjects()      — subscribes to ALL objects (use sparingly, for debug)
 */
import { useSyncExternalStore, useCallback, useMemo } from 'react'
import { getStore, type Store } from '@/data'
import type { Field, VirtualObject } from '@/data/types'

export function useStore(): Store {
  return getStore()
}

/** Subscribe to a single VirtualObject — re-renders on any op affecting its id. */
export function useVirtualObject(id: string): VirtualObject | undefined {
  const store = getStore()
  const subscribe = useCallback(
    (cb: () => void) => store.subscribe(id, cb),
    [store, id],
  )
  const getSnapshot = useCallback(() => store.get(id), [store, id])
  return useSyncExternalStore(subscribe, getSnapshot, getSnapshot)
}

/** Subscribe to a projection result — re-renders when underlying object changes. */
export function useProjection(id: string, projectionName: string): Field[] {
  const store = getStore()
  const subscribe = useCallback(
    (cb: () => void) => store.subscribe(id, cb),
    [store, id],
  )
  const getSnapshot = useCallback(
    () => store.version(id),
    [store, id],
  )
  // Re-run resolve only when version bumps (useSyncExternalStore snapshot changes)
  const version = useSyncExternalStore(subscribe, getSnapshot, getSnapshot)
  return useMemo(
    () => store.resolve(id, projectionName),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [store, id, projectionName, version],
  )
}

/**
 * Subscribe to ALL objects by virtualType filter.
 * Re-renders whenever any matching object changes.
 * Use sparingly — costs = all matching signal subscribes.
 */
export function useObjectsByType(virtualType: string): VirtualObject[] {
  const store = getStore()
  // Coarse: subscribe to a sentinel we bump manually; or walk all signals.
  // For now, poll-on-change via a generic global tick signal — use global subscribe.
  const subscribe = useCallback(
    (cb: () => void) => {
      // Subscribe to every current object; good enough for Phase 1a.
      const unsubs = store.all().map((o) => store.subscribe(o.id, cb))
      return () => unsubs.forEach((u) => u())
    },
    [store],
  )
  const getSnapshot = useCallback(() => {
    return store
      .all()
      .filter((o) => o.virtualType === virtualType)
      .map((o) => o.id)
      .join(',')
  }, [store, virtualType])
  const snapshot = useSyncExternalStore(subscribe, getSnapshot, getSnapshot)
  return useMemo(
    () => store.all().filter((o) => o.virtualType === virtualType),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [store, virtualType, snapshot],
  )
}
