/**
 * TypeHierarchy — tree view of runtime objects grouped by type.
 *
 * Shows: virtualType hierarchy → runtimeType badges → per-object fields/version.
 * Independent panel for inspecting the full Data + Runtime Layer state.
 *
 * Types of projection visible:
 *  - By virtualType (e.g. channel / message / document / counter)
 *  - By runtimeType (virtual / signal / vfs / replicache / ...)
 *  - By path hierarchy (pchat/channels/... subtree)
 */
import { useMemo, useState, useSyncExternalStore, useCallback } from 'react'
import { getStore } from '@/data'
import { getRuntime } from '@/runtime'
import type { VirtualObject } from '@/data/types'
import type { RuntimeObject } from '@/runtime/types'

type GroupBy = 'virtualType' | 'runtimeType' | 'path'

export function TypeHierarchy() {
  const [groupBy, setGroupBy] = useState<GroupBy>('virtualType')
  const [expanded, setExpanded] = useState<Set<string>>(new Set())

  // Subscribe to ALL objects — re-render when anything changes
  const [version, updateVersion] = useStoreAllVersion()

  const store = getStore()
  const runtime = getRuntime()

  const data = useMemo(() => {
    // Touch `version` so memo invalidates on signal bumps
    void version
    // Primary source: runtime objects (covers ALL runtimeTypes, not just store-backed).
    // For each RuntimeObject, ask its adapter for the current VirtualObject view.
    const ros = runtime.allObjects()
    const storeByIds = new Set(ros.map((r) => r.id))
    const vosFromRuntime = ros
      .map((ro) => runtime.readObject(ro.id))
      .filter((v): v is VirtualObject => !!v)
    // Include store-only objects (rare, but covers objects ingested without instantiate)
    const storeOnly = store.all().filter((o) => !storeByIds.has(o.id))
    return buildHierarchy([...vosFromRuntime, ...storeOnly], ros, groupBy)
  }, [version, groupBy, store, runtime])

  const toggleGroup = (key: string) => {
    const next = new Set(expanded)
    if (next.has(key)) next.delete(key)
    else next.add(key)
    setExpanded(next)
  }

  return (
    <div className="p-2 text-[11px] font-mono overflow-auto h-full"
      style={{ fontFamily: '"JetBrains Mono", monospace', background: '#1a1a2e', color: '#e0e0f0' }}>
      <div className="flex gap-2 mb-2 pb-2 border-b" style={{ borderColor: '#333366' }}>
        <span className="text-[10px] opacity-60">group by:</span>
        {(['virtualType', 'runtimeType', 'path'] as GroupBy[]).map((g) => (
          <button
            key={g}
            onClick={() => setGroupBy(g)}
            className={`text-[10px] px-2 py-0.5 rounded ${
              groupBy === g ? 'bg-purple-600' : 'opacity-60 hover:opacity-100'
            }`}
            style={{ background: groupBy === g ? '#6c63ff' : 'transparent', border: '1px solid #333366' }}
          >
            {g}
          </button>
        ))}
        <span className="ml-auto text-[10px] opacity-60">
          {data.totalObjects} objects · {data.totalOps} ops
        </span>
        <button
          onClick={updateVersion}
          className="text-[10px] px-2 py-0.5 opacity-60 hover:opacity-100"
          style={{ border: '1px solid #333366' }}
        >
          ⟳
        </button>
      </div>

      {data.groups.map((group) => (
        <Group
          key={group.key}
          group={group}
          expanded={expanded.has(group.key)}
          onToggle={() => toggleGroup(group.key)}
        />
      ))}
    </div>
  )
}

// ── Group + Object rows ──

interface Group {
  key: string
  label: string
  color: string
  items: HierarchyItem[]
}

interface HierarchyItem {
  object: VirtualObject
  runtime?: RuntimeObject
}

function Group({ group, expanded, onToggle }: {
  group: Group
  expanded: boolean
  onToggle: () => void
}) {
  return (
    <div className="mb-1">
      <div
        onClick={onToggle}
        className="cursor-pointer py-0.5 flex items-center gap-2 hover:opacity-100"
      >
        <span style={{ color: '#888aa' }}>{expanded ? '▾' : '▸'}</span>
        <span
          className="text-[10px] px-1.5 py-0.5 rounded"
          style={{ background: `${group.color}22`, color: group.color, border: `1px solid ${group.color}44` }}
        >
          {group.label}
        </span>
        <span className="text-[10px] opacity-50">[{group.items.length}]</span>
      </div>
      {expanded && (
        <div className="ml-4 mt-0.5">
          {group.items.map((item) => (
            <ObjectRow key={item.object.id} item={item} />
          ))}
        </div>
      )}
    </div>
  )
}

function ObjectRow({ item }: { item: HierarchyItem }) {
  const [open, setOpen] = useState(false)
  const runtimeType = item.runtime?.runtimeType ?? '—'
  const runtimeColor = runtimeTypeColor(runtimeType)

  return (
    <div className="py-0.5">
      <div
        onClick={() => setOpen(!open)}
        className="cursor-pointer flex items-center gap-1.5 hover:opacity-100"
      >
        <span style={{ color: '#8888aa', width: 10 }}>{open ? '▾' : '▸'}</span>
        <span className="opacity-80">{item.object.id}</span>
        <span className="text-[9px] opacity-50">v{item.object.version}</span>
        <span
          className="text-[9px] px-1 rounded"
          style={{ background: `${runtimeColor}22`, color: runtimeColor }}
        >
          {runtimeType}
        </span>
        <span className="text-[9px] opacity-50 ml-auto">
          {item.object.fields.size} fields
        </span>
      </div>
      {open && (
        <div className="ml-6 mt-0.5">
          {Array.from(item.object.fields.entries()).map(([name, field]) => (
            <div key={name} className="flex gap-2 text-[10px] py-0.5">
              <span style={{ color: '#66ccff' }}>{name}</span>
              <span style={{ color: '#888aa' }}>:{field.type}</span>
              <span className="opacity-70 truncate" style={{ maxWidth: 300 }}>
                {formatValue(field.content)}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// ── Helpers ──

function buildHierarchy(
  vos: VirtualObject[],
  ros: RuntimeObject[],
  groupBy: GroupBy,
): { groups: Group[]; totalObjects: number; totalOps: number } {
  const roById = new Map(ros.map((r) => [r.id, r]))
  const items: HierarchyItem[] = vos.map((vo) => ({
    object: vo,
    runtime: roById.get(vo.id),
  }))

  const buckets = new Map<string, HierarchyItem[]>()
  for (const it of items) {
    const key =
      groupBy === 'virtualType'
        ? it.object.virtualType
        : groupBy === 'runtimeType'
          ? (it.runtime?.runtimeType ?? 'unregistered')
          : firstSegment(it.object.id)
    const list = buckets.get(key) ?? []
    list.push(it)
    buckets.set(key, list)
  }

  const groups: Group[] = Array.from(buckets.entries())
    .map(([key, groupItems]) => ({
      key,
      label: key,
      color:
        groupBy === 'runtimeType'
          ? runtimeTypeColor(key)
          : virtualTypeColor(key),
      items: groupItems.sort((a, b) => a.object.id.localeCompare(b.object.id)),
    }))
    .sort((a, b) => a.label.localeCompare(b.label))

  return {
    groups,
    totalObjects: items.length,
    totalOps: getStore().allOps().length,
  }
}

function firstSegment(path: string): string {
  const [first] = path.split('/')
  return first || 'root'
}

function runtimeTypeColor(t: string): string {
  switch (t) {
    case 'virtual': return '#8888aa'
    case 'signal': return '#44dd88'
    case 'vfs': return '#ffcc66'
    case 'replicache': return '#6c63ff'
    case 'lexical': return '#ff99cc'
    case 'quickjs': return '#ff5566'
    case 'crdt': return '#c084fc'
    default: return '#666666'
  }
}

function virtualTypeColor(t: string): string {
  // deterministic hash-based color picking from a palette
  const palette = ['#66ccff', '#44dd88', '#ffcc66', '#ff99cc', '#c084fc', '#ff5566', '#6c63ff', '#88ffaa']
  let h = 0
  for (let i = 0; i < t.length; i++) h = (h * 31 + t.charCodeAt(i)) | 0
  return palette[Math.abs(h) % palette.length]
}

function formatValue(v: unknown): string {
  if (v === null || v === undefined) return 'null'
  if (typeof v === 'string') return v.length > 80 ? v.slice(0, 80) + '…' : v
  if (typeof v === 'object') return JSON.stringify(v).slice(0, 80)
  return String(v)
}

// ── Hook: subscribe to any store change ──

function useStoreAllVersion(): [number, () => void] {
  const store = getStore()
  const runtime = getRuntime()
  const subscribe = useCallback(
    (cb: () => void) => {
      // Subscribe via runtime layer — works for virtual / signal / vfs / others.
      let unsubs = runtime
        .allObjects()
        .map((ro) => runtime.subscribeObject(ro.id, cb))
      // Poll for newly-created objects (no global "objects added" signal yet)
      const rebind = () => {
        unsubs.forEach((u) => u())
        unsubs = runtime
          .allObjects()
          .map((ro) => runtime.subscribeObject(ro.id, cb))
        cb()
      }
      const interval = setInterval(rebind, 500)
      return () => {
        clearInterval(interval)
        unsubs.forEach((u) => u())
      }
    },
    [runtime],
  )
  // Snapshot = store cookie + runtime object count (bumps on new instantiate too)
  const getSnapshot = useCallback(
    () => (store.cookie() as number) * 1000 + runtime.allObjects().length,
    [store, runtime],
  )
  const version = useSyncExternalStore(subscribe, getSnapshot, getSnapshot)

  // Force-refresh handle
  const [, setTick] = useState(0)
  const force = useCallback(() => setTick((v) => v + 1), [])

  return [version, force]
}
