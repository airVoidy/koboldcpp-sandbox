// Three-AABB list layout. Each list gets three zones (-1 / 0 / +1) where items
// can be freely placed and moved. The zones are NOT a strict notation — they
// are bounded buckets the user/agent mutates as needed. Per the architecture
// agreement, [-1]/[0]/[+1] is informal shorthand, not a forced schema.
//
// See: docs/ATOMIC_AABB_LIST_LAYOUT_V0_1.md

import type { AtomicStore } from './store'

export type Zone = -1 | 0 | 1

export type Aabb = { x: number; y: number; w: number; h: number }

export type AabbZone = {
  /** Item ids currently parked in this zone, in insertion order. */
  items: string[]
  /** Optional bounding box for visual placement. */
  aabb?: Aabb
}

export type AabbList = {
  id: string
  /** Reference to the AtomicList this layout belongs to (source of items). */
  listId: string
  zones: { '-1': AabbZone; '0': AabbZone; '+1': AabbZone }
}

const ZONE_KEYS: Record<Zone, keyof AabbList['zones']> = {
  [-1]: '-1',
  [0]: '0',
  [1]: '+1',
}

export class AabbLayout {
  readonly layouts = new Map<string, AabbList>()

  constructor(readonly store: AtomicStore) {}

  /**
   * Build a layout for a list. The current list items go into zone 0 by
   * default; zones -1 and +1 start empty.
   */
  createLayout(layoutId: string, listId: string): AabbList {
    const list = this.store.lists.get(listId)
    if (!list) throw new Error(`list ${listId} not found`)

    const layout: AabbList = {
      id: layoutId,
      listId,
      zones: {
        '-1': { items: [] },
        '0': { items: [...list.items] },
        '+1': { items: [] },
      },
    }
    this.layouts.set(layoutId, layout)
    return layout
  }

  getLayout(layoutId: string): AabbList | undefined {
    return this.layouts.get(layoutId)
  }

  /** Move an item from one zone to another. */
  moveItem(layoutId: string, itemId: string, fromZone: Zone, toZone: Zone): AabbList {
    const layout = this.requireLayout(layoutId)
    const fromKey = ZONE_KEYS[fromZone]
    const toKey = ZONE_KEYS[toZone]

    const fromArr = layout.zones[fromKey].items
    const idx = fromArr.indexOf(itemId)
    if (idx === -1) {
      throw new Error(`item ${itemId} not in zone ${fromZone}`)
    }
    fromArr.splice(idx, 1)
    if (!layout.zones[toKey].items.includes(itemId)) {
      layout.zones[toKey].items.push(itemId)
    }
    return layout
  }

  /** Add an item to a zone (no-op if already there). */
  addToZone(layoutId: string, itemId: string, zone: Zone): AabbList {
    const layout = this.requireLayout(layoutId)
    const key = ZONE_KEYS[zone]
    if (!layout.zones[key].items.includes(itemId)) {
      layout.zones[key].items.push(itemId)
    }
    return layout
  }

  /** Remove an item from a zone (no-op if absent). */
  removeFromZone(layoutId: string, itemId: string, zone: Zone): AabbList {
    const layout = this.requireLayout(layoutId)
    const key = ZONE_KEYS[zone]
    const arr = layout.zones[key].items
    const idx = arr.indexOf(itemId)
    if (idx >= 0) arr.splice(idx, 1)
    return layout
  }

  /** Set the bounding box for a zone (purely visual hint). */
  setAabb(layoutId: string, zone: Zone, aabb: Aabb): AabbList {
    const layout = this.requireLayout(layoutId)
    const key = ZONE_KEYS[zone]
    layout.zones[key].aabb = { ...aabb }
    return layout
  }

  /**
   * Promote: move an item from +1 (future) into 0 (current). Convenience for
   * "checkpoint reached, the optimistic item became real".
   */
  checkpoint(layoutId: string, itemId: string): AabbList {
    const layout = this.requireLayout(layoutId)
    if (layout.zones['+1'].items.includes(itemId)) {
      this.moveItem(layoutId, itemId, 1, 0)
    }
    return layout
  }

  /**
   * Demote: move an item from 0 (current) into -1 (history). Convenience for
   * "this item is no longer current, but kept as historical reference".
   */
  archive(layoutId: string, itemId: string): AabbList {
    const layout = this.requireLayout(layoutId)
    if (layout.zones['0'].items.includes(itemId)) {
      this.moveItem(layoutId, itemId, 0, -1)
    }
    return layout
  }

  /** All items across zones, ordered -1 → 0 → +1. */
  flatten(layoutId: string): string[] {
    const layout = this.requireLayout(layoutId)
    return [
      ...layout.zones['-1'].items,
      ...layout.zones['0'].items,
      ...layout.zones['+1'].items,
    ]
  }

  /** Find which zone (if any) holds an item. */
  zoneOf(layoutId: string, itemId: string): Zone | null {
    const layout = this.requireLayout(layoutId)
    if (layout.zones['-1'].items.includes(itemId)) return -1
    if (layout.zones['0'].items.includes(itemId)) return 0
    if (layout.zones['+1'].items.includes(itemId)) return 1
    return null
  }

  private requireLayout(layoutId: string): AabbList {
    const layout = this.layouts.get(layoutId)
    if (!layout) throw new Error(`layout ${layoutId} not found`)
    return layout
  }
}
