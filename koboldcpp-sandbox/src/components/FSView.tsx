/**
 * FSView — virtual filesystem view over sandbox runtime objects.
 *
 * Mirrors vanilla pipeline-chat FS tab: tree with inline meta/data.
 * FS = Source of Truth representation.
 * JSONL apply-patch = commands that change projection.
 */
import { useState, useCallback, useEffect } from 'react'
import type { Sandbox, SandboxNode, FieldCell } from '@/lib/sandbox'

const TK = {
  bg: '#1a1a2e',
  surface: '#222244',
  border: '#333366',
  text: '#e0e0f0',
  dim: '#8888aa',
  accent: '#6c63ff',
  green: '#44dd88',
  yellow: '#ffcc66',
  red: '#ff5566',
  purple: '#c084fc',
  cyan: '#66ccff',
}

interface FSViewProps {
  sandbox: Sandbox
  onSelect?: (node: SandboxNode, path: string) => void
}

export function FSView({ sandbox, onSelect }: FSViewProps) {
  const roots = sandbox.roots()
  const fieldCount = sandbox.fieldStore.size

  return (
    <div className="text-xs overflow-y-auto h-full p-2"
      style={{ fontFamily: '"JetBrains Mono", monospace', background: TK.bg }}>
      <div className="mb-1 text-[10px] flex items-center justify-between" style={{ color: TK.dim }}>
        <span>{sandbox.tree.size} nodes</span>
        {fieldCount > 0 && <span>{fieldCount} fields</span>}
        <span style={{ color: TK.purple }}>{sandbox.execLog.length} exec</span>
      </div>
      {roots.length === 0 ? (
        <div className="text-[10px] py-4 text-center" style={{ color: TK.dim }}>
          empty — loadServerState() or exec('mk', ...)
        </div>
      ) : (
        roots.map(node => (
          <NodeTree
            key={node.path}
            sandbox={sandbox}
            node={node}
            depth={0}
            onSelect={onSelect}
          />
        ))
      )}
    </div>
  )
}

// ── Node tree with inline meta/data (vanilla-style) ──

function NodeTree({ sandbox, node, depth, onSelect }: {
  sandbox: Sandbox
  node: SandboxNode
  depth: number
  onSelect?: (node: SandboxNode, path: string) => void
}) {
  const [expanded, setExpanded] = useState(depth < 2)
  const [showData, setShowData] = useState(false)
  const [showFields, setShowFields] = useState(false)

  const hasChildren = node.children.length > 0
  const isDeleted = !!node.data._deleted

  const handleToggle = useCallback(() => {
    setExpanded(v => !v)
  }, [])

  const handleSelect = useCallback(() => {
    sandbox.exec('cd', { path: node.path }, '_ui')
    onSelect?.(node, node.path)
  }, [sandbox, node, onSelect])

  const childNodes = node.children
    .map(p => sandbox.resolve(p))
    .filter(Boolean) as SandboxNode[]

  const dataKeys = Object.keys(node.data).filter(k => k !== '_deleted')
  const hasData = dataKeys.length > 0

  // Fields from fieldStore for this node
  const nodeFields = getNodeFields(sandbox, node.path)

  const indent = depth * 16

  return (
    <div style={{ opacity: isDeleted ? 0.4 : 1 }}>
      {/* Node header — click name to select, click arrow to expand */}
      <div className="flex items-center gap-1 py-0.5" style={{ paddingLeft: indent }}>
        {/* Expand toggle */}
        <span
          className="cursor-pointer select-none"
          style={{ color: TK.dim, width: 12, display: 'inline-block', textAlign: 'center' }}
          onClick={handleToggle}
        >
          {(hasChildren || hasData) ? (expanded ? '▾' : '▸') : '·'}
        </span>

        {/* Node name — click to select */}
        <span
          className="cursor-pointer hover:underline"
          style={{ color: TK.text, fontWeight: depth < 2 ? 700 : 400 }}
          onClick={handleSelect}
        >
          {node.name}
        </span>

        {/* Child count */}
        {hasChildren && (
          <span className="text-[9px]" style={{ color: TK.dim }}>
            [{node.children.length}]
          </span>
        )}
      </div>

      {/* Expanded content: meta + data inline (vanilla-style) */}
      {expanded && (
        <div style={{ paddingLeft: indent + 16 }}>
          {/* Meta block — always shown when expanded */}
          {Object.keys(node.meta).length > 0 && (
            <InlineJson data={node.meta} />
          )}

          {/* Data block — toggle with "── data ──" separator */}
          {hasData && (
            <>
              <div
                className="text-[9px] cursor-pointer py-0.5 hover:opacity-80"
                style={{ color: TK.dim }}
                onClick={() => setShowData(v => !v)}
              >
                {showData ? '── data ──' : '── data ── (click)'}
              </div>
              {showData && <InlineJson data={
                Object.fromEntries(Object.entries(node.data).filter(([k]) => k !== '_deleted'))
              } />}
            </>
          )}

          {/* Fields from fieldStore */}
          {nodeFields.length > 0 && (
            <>
              <div
                className="text-[9px] cursor-pointer py-0.5 hover:opacity-80"
                style={{ color: TK.cyan }}
                onClick={() => setShowFields(v => !v)}
              >
                {showFields ? '▾' : '▸'} fields [{nodeFields.length}]
              </div>
              {showFields && (
                <div className="ml-2 mb-1">
                  {nodeFields.map(f => (
                    <div key={f.path} className="text-[9px] py-0.5 flex gap-2">
                      <span style={{ color: TK.cyan }}>{f.localName}</span>
                      <span style={{ color: TK.dim }}>=</span>
                      <span style={{ color: TK.text }}>
                        {typeof f.value === 'object' ? JSON.stringify(f.value) : String(f.value ?? 'null')}
                      </span>
                      {f.bind && (
                        <span className="text-[8px]" style={{ color: TK.purple }}>
                          → {f.bind}
                        </span>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </>
          )}

          {/* Deleted marker */}
          {isDeleted && (
            <div className="text-[9px] my-0.5" style={{ color: TK.red }}>
              [DELETED]
            </div>
          )}

          {/* Children */}
          {childNodes.map(child => (
            <NodeTree
              key={child.path}
              sandbox={sandbox}
              node={child}
              depth={depth + 1}
              onSelect={onSelect}
            />
          ))}
        </div>
      )}
    </div>
  )
}

// ── Inline JSON block (vanilla-style) ──

function InlineJson({ data }: { data: unknown }) {
  return (
    <pre className="text-[10px] whitespace-pre-wrap leading-relaxed my-0.5"
      style={{ color: TK.cyan }}>
      {JSON.stringify(data, null, 2)}
    </pre>
  )
}

// ── Helpers ──

function getNodeFields(sandbox: Sandbox, nodePath: string): FieldCell[] {
  const result: FieldCell[] = []
  for (const [path, cell] of sandbox.fieldStore) {
    if (path.startsWith(nodePath + '.') || cell.ref === nodePath) {
      result.push(cell)
    }
  }
  return result
}
