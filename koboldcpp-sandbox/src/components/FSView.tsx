/**
 * FSView — virtual filesystem view over sandbox runtime objects.
 *
 * Like vanilla pipeline-chat FS tab: tree of nodes with expandable meta/data.
 * All data from runtime objects in memory, not from disk.
 */
import { useState, useCallback } from 'react'
import { ChevronDown, ChevronRight, FolderOpen, Folder, FileText, Hash } from 'lucide-react'
import type { SandboxNode } from '@/lib/sandbox'

const TK = {
  bg: '#1a1a2e',
  surface: '#222244',
  surface2: '#2a2a4a',
  border: '#333366',
  text: '#e0e0f0',
  dim: '#8888aa',
  accent: '#6c63ff',
  green: '#44dd88',
  yellow: '#ffcc66',
  red: '#ff5566',
  purple: '#c084fc',
}

interface FSViewProps {
  root: SandboxNode
  onSelect?: (node: SandboxNode, path: string) => void
}

export function FSView({ root, onSelect }: FSViewProps) {
  return (
    <div className="text-xs overflow-y-auto h-full p-2" style={{ fontFamily: '"JetBrains Mono", monospace' }}>
      <div className="mb-1 text-[10px] uppercase" style={{ color: TK.dim }}>
        sandbox
      </div>
      <NodeTree node={root} path="" depth={0} onSelect={onSelect} />
    </div>
  )
}

function NodeTree({ node, path, depth, onSelect }: {
  node: SandboxNode
  path: string
  depth: number
  onSelect?: (node: SandboxNode, path: string) => void
}) {
  const [expanded, setExpanded] = useState(depth < 2)
  const [showMeta, setShowMeta] = useState(false)
  const [showData, setShowData] = useState(false)
  const [showExec, setShowExec] = useState(false)

  const fullPath = path ? `${path}/${node.name}` : node.name
  const hasChildren = node.children.size > 0
  const isDeleted = !!node.data._deleted

  const handleClick = useCallback(() => {
    if (hasChildren) setExpanded(v => !v)
    onSelect?.(node, fullPath)
  }, [hasChildren, node, fullPath, onSelect])

  const typeColor = node.type === 'channel' ? TK.green
    : node.type === 'message' ? TK.accent
    : node.type === 'channels' ? TK.yellow
    : TK.dim

  return (
    <div style={{ opacity: isDeleted ? 0.4 : 1 }}>
      {/* Node header */}
      <div
        className="flex items-center gap-1 py-0.5 cursor-pointer hover:opacity-80"
        style={{ paddingLeft: depth * 16 }}
        onClick={handleClick}
      >
        {/* Expand icon */}
        {hasChildren ? (
          expanded
            ? <ChevronDown size={12} style={{ color: TK.dim }} />
            : <ChevronRight size={12} style={{ color: TK.dim }} />
        ) : (
          <span style={{ width: 12 }} />
        )}

        {/* Folder/file icon */}
        {hasChildren ? (
          expanded
            ? <FolderOpen size={12} style={{ color: TK.yellow }} />
            : <Folder size={12} style={{ color: TK.yellow }} />
        ) : (
          <FileText size={12} style={{ color: TK.dim }} />
        )}

        {/* Name */}
        <span style={{ color: TK.text, fontWeight: depth < 2 ? 600 : 400 }}>
          {node.name}
        </span>

        {/* Type badge */}
        {node.type && (
          <span className="text-[9px] px-1 rounded" style={{ color: typeColor, background: `${typeColor}15` }}>
            {node.type}
          </span>
        )}

        {/* Children count */}
        {hasChildren && (
          <span className="text-[9px]" style={{ color: TK.dim }}>
            [{node.children.size}]
          </span>
        )}

        {/* Exec count */}
        {node.exec.length > 0 && (
          <span className="text-[9px]" style={{ color: TK.purple }}>
            <Hash size={8} className="inline" />{node.exec.length}
          </span>
        )}
      </div>

      {/* Meta/Data/Exec toggles (when expanded) */}
      {expanded && (
        <div style={{ paddingLeft: (depth + 1) * 16 + 12 }}>
          {/* Meta */}
          {Object.keys(node.meta).length > 0 && (
            <div>
              <button
                onClick={() => setShowMeta(v => !v)}
                className="text-[9px] py-0.5 hover:opacity-80"
                style={{ color: TK.dim }}
              >
                {showMeta ? '▾' : '▸'} _meta
              </button>
              {showMeta && (
                <pre className="text-[10px] p-1 rounded mt-0.5 mb-1 whitespace-pre-wrap"
                  style={{ background: TK.bg, color: TK.text }}>
                  {JSON.stringify(node.meta, null, 2)}
                </pre>
              )}
            </div>
          )}

          {/* Data */}
          {Object.keys(node.data).filter(k => k !== '_deleted').length > 0 && (
            <div>
              <button
                onClick={() => setShowData(v => !v)}
                className="text-[9px] py-0.5 hover:opacity-80"
                style={{ color: TK.dim }}
              >
                {showData ? '▾' : '▸'} _data
              </button>
              {showData && (
                <pre className="text-[10px] p-1 rounded mt-0.5 mb-1 whitespace-pre-wrap"
                  style={{ background: TK.bg, color: TK.text }}>
                  {JSON.stringify(
                    Object.fromEntries(Object.entries(node.data).filter(([k]) => k !== '_deleted')),
                    null, 2
                  )}
                </pre>
              )}
            </div>
          )}

          {/* Exec log */}
          {node.exec.length > 0 && (
            <div>
              <button
                onClick={() => setShowExec(v => !v)}
                className="text-[9px] py-0.5 hover:opacity-80"
                style={{ color: TK.purple }}
              >
                {showExec ? '▾' : '▸'} _exec [{node.exec.length}]
              </button>
              {showExec && (
                <div className="mt-0.5 mb-1">
                  {node.exec.map((e, i) => (
                    <div key={i} className="text-[9px] py-0.5" style={{ color: TK.dim }}>
                      <span style={{ color: TK.accent }}>{e.op}</span>
                      {' '}
                      <span style={{ color: TK.dim }}>
                        {new Date(e.ts).toLocaleTimeString()}
                      </span>
                      {' '}
                      <span style={{ color: TK.green }}>{e.user}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Children */}
          {Array.from(node.children.values()).map(child => (
            <NodeTree
              key={child.name}
              node={child}
              path={fullPath}
              depth={depth + 1}
              onSelect={onSelect}
            />
          ))}
        </div>
      )}
    </div>
  )
}
