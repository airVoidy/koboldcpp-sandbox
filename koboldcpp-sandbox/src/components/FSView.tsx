/**
 * FSView — virtual filesystem view over sandbox runtime objects.
 *
 * Mirrors vanilla pipeline-chat FS tab: tree with inline meta/data.
 * FS = Source of Truth representation.
 * JSONL apply-patch = commands that change projection.
 */
import { useState, useCallback } from 'react'
import type { Sandbox, SandboxNode, FieldCell } from '@/lib/sandbox'

const TK = {
  bg: '#1a1a2e',
  dim: '#8888aa',
  text: '#e0e0f0',
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
  const nodeFields = getNodeFields(sandbox, node.path)
  const listKinds = Object.keys(node.childLists).sort((a, b) => a.localeCompare(b, undefined, { numeric: true }))
  const indent = depth * 16

  return (
    <div style={{ opacity: isDeleted ? 0.4 : 1 }}>
      <div className="flex items-center gap-1 py-0.5" style={{ paddingLeft: indent }}>
        <span
          className="cursor-pointer select-none"
          style={{ color: TK.dim, width: 12, display: 'inline-block', textAlign: 'center' }}
          onClick={handleToggle}
        >
          {(hasChildren || hasData) ? (expanded ? '▾' : '▸') : '·'}
        </span>

        <span
          className="cursor-pointer hover:underline"
          style={{ color: TK.text, fontWeight: depth < 2 ? 700 : 400 }}
          onClick={handleSelect}
        >
          {node.name}
        </span>

        {hasChildren && (
          <span className="text-[9px]" style={{ color: TK.dim }}>
            [{node.children.length}]
          </span>
        </div>
        {roots.length === 0 ? (
          <div className="text-[10px] py-4 text-center" style={{ color: TK.dim }}>
            empty — run loadServerState() or exec('mk', ...)
          </div>
        ) : (
          roots.map(node => (
            <NodeTree
              key={node.path}
              sandbox={sandbox}
              node={node}
              depth={0}
              selectedPath={selectedPath}
              onSelect={handleSelect}
            />
          ))
        )}
      </div>

      {expanded && (
        <div style={{ paddingLeft: indent + 16 }}>
          {Object.keys(node.meta).length > 0 && (
            <InlineJson data={node.meta} />
          )}

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

          <div className="text-[9px] py-0.5" style={{ color: TK.dim }}>
            children[]: {node.capabilities.children ? 'open' : 'closed'}
            {Array.isArray(node.capabilities.children) && ` (${node.capabilities.children.join(', ')})`}
          </div>

          {listKinds.length > 0 && (
            <div className="ml-2 mb-1">
              <div className="text-[9px] py-0.5" style={{ color: TK.purple }}>
                virtual lists
              </div>
              {listKinds.map(kind => (
                <div key={kind} className="text-[9px] py-0.5">
                  {(() => {
                    const scope = sandbox.typedScope(node.path, kind)
                    if (!scope) return null
                    return (
                      <>
                  <div className="flex gap-2">
                    <span style={{ color: TK.purple }}>{kind}[</span>
                    <span style={{ color: TK.dim }}>{scope.items.length}</span>
                    <span style={{ color: TK.purple }}>]</span>
                  </div>
                  <div className="ml-3" style={{ color: TK.dim }}>
                    <span>0=template</span>
                    {scope.template.virtual ? (
                      <span> (virtual)</span>
                    ) : (
                      <span> (local)</span>
                    )}
                    <span>, instances={scope.items.filter(item => item.role === 'instance').length}</span>
                  </div>
                  <div className="ml-3" style={{ color: TK.dim }}>
                    <span>{scope.scopePath}</span>
                  </div>
                  <div className="ml-3" style={{ color: TK.dim }}>
                    <span>{scope.instancePattern}</span>
                  </div>
                      </>
                    )
                  })()}
                </div>
              ))}
            </div>
          )}

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

          {isDeleted && (
            <div className="text-[9px] my-0.5" style={{ color: TK.red }}>
              [DELETED]
            </div>
          )}

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

function InlineJson({ data }: { data: unknown }) {
  return (
    <pre className="text-[10px] whitespace-pre-wrap leading-relaxed my-0.5"
      style={{ color: TK.cyan }}>
      {JSON.stringify(data, null, 2)}
    </pre>
  )
}

function getNodeFields(sandbox: Sandbox, nodePath: string): FieldCell[] {
  const result: FieldCell[] = []
  for (const [path, cell] of sandbox.fieldStore) {
    if (path.startsWith(nodePath + '.') || cell.ref === nodePath) {
      result.push(cell)
    }
  }
  return result
}
