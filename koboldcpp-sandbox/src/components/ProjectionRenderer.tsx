/**
 * ProjectionRenderer — renders any Projection as a field table.
 *
 * Generic: works for any node type.
 * Shows flat_store fields with hash, path, value, type.
 * Supports view switching (all, _meta, _data).
 */
import { useState } from 'react'
import type { Projection, ProjectionFieldRow } from '@/types/runtime'

interface Props {
  projection: Projection
  compact?: boolean
}

export function ProjectionRenderer({ projection, compact }: Props) {
  const [activeView, setActiveView] = useState('all')

  const viewNames = Object.keys(projection.views ?? {})
  const rows: ProjectionFieldRow[] = projection.views?.[activeView] ?? []

  if (compact) {
    return (
      <div className="text-[10px] text-[var(--text-dim)] mt-1 space-y-0.5">
        {rows.map(row => (
          <div key={row.path} className="flex gap-2">
            <span className="text-[var(--accent)] font-mono">{row.path}</span>
            <span className="truncate">{formatValue(row.value)}</span>
          </div>
        ))}
      </div>
    )
  }

  return (
    <div className="border border-[var(--border)] rounded-lg overflow-hidden">
      {/* View tabs */}
      {viewNames.length > 1 && (
        <div className="flex border-b border-[var(--border)] bg-[var(--surface)]">
          {viewNames.map(name => (
            <button
              key={name}
              onClick={() => setActiveView(name)}
              className={`px-3 py-1 text-[10px] font-mono transition-colors ${
                activeView === name
                  ? 'text-[var(--accent)] border-b border-[var(--accent)]'
                  : 'text-[var(--text-dim)] hover:text-[var(--text)]'
              }`}
            >
              {name} ({(projection.views?.[name] ?? []).length})
            </button>
          ))}
        </div>
      )}

      {/* Field table */}
      <table className="w-full text-[11px]">
        <thead>
          <tr className="bg-[var(--surface)] text-[var(--text-dim)]">
            <th className="text-left px-2 py-1 font-normal">path</th>
            <th className="text-left px-2 py-1 font-normal">value</th>
            <th className="text-left px-2 py-1 font-normal w-16">hash</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(row => (
            <tr key={row.path} className="border-t border-[var(--border)] hover:bg-[var(--surface2)]">
              <td className="px-2 py-1 font-mono text-[var(--accent)]">{row.path}</td>
              <td className="px-2 py-1 truncate max-w-[300px]">{formatValue(row.value)}</td>
              <td className="px-2 py-1 font-mono text-[var(--text-dim)] text-[9px]">{row.hash?.slice(0, 8)}</td>
            </tr>
          ))}
        </tbody>
      </table>

      {rows.length === 0 && (
        <div className="px-3 py-4 text-center text-[var(--text-dim)] text-xs">
          No fields in view "{activeView}"
        </div>
      )}

      {/* Source info */}
      <div className="px-2 py-1 bg-[var(--surface)] text-[9px] text-[var(--text-dim)] border-t border-[var(--border)]">
        source: {projection.source_node} | fields: {projection.fields?.length ?? 0}
      </div>
    </div>
  )
}

function formatValue(value: unknown): string {
  if (value === null || value === undefined) return 'null'
  if (typeof value === 'string') return value.length > 80 ? value.slice(0, 80) + '...' : value
  if (typeof value === 'object') return JSON.stringify(value).slice(0, 80)
  return String(value)
}
