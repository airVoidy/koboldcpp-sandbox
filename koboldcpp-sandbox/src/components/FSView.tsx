/**
 * FSView — virtual filesystem view over sandbox runtime objects.
 *
 * Sandbox middleware: shows runtime tree with expandable meta/data/exec.
 * All data from runtime objects in memory, not from disk.
 * Navigation = exec entry {op: 'cd', path}.
 */
import { useState, useCallback } from 'react'
import { ChevronDown, ChevronRight, FolderOpen, Folder, FileText, Hash, Eye } from 'lucide-react'
import type { Sandbox, SandboxNode } from '@/lib/sandbox'

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
  sandbox: Sandbox
  onSelect?: (node: SandboxNode, path: string) => void
}

export function FSView({ sandbox, onSelect }: FSViewProps) {
  const [selectedPath, setSelectedPath] = useState<string | null>(null)
  const roots = sandbox.roots()

  const handleSelect = useCallback((node: SandboxNode, path: string) => {
    setSelectedPath(path)
    // Navigation is also an exec entry
    sandbox.exec('cd', { path }, '_ui')
    onSelect?.(node, path)
  }, [sandbox, onSelect])

  const selectedNode = selectedPath ? sandbox.resolve(selectedPath) : null

  return (
    <div className="flex h-full" style={{ fontFamily: '"JetBrains Mono", monospace' }}>
      {/* Tree panel */}
      <div className="flex-1 text-xs overflow-y-auto p-2 min-w-0">
        <div className="mb-1 text-[10px] uppercase flex items-center justify-between" style={{ color: TK.dim }}>
          <span>sandbox ({sandbox.tree.size} nodes)</span>
          <span className="text-[9px]" style={{ color: TK.purple }}>
            {sandbox.execLog.length} exec
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

      {/* Detail panel */}
      {selectedNode && (
        <div className="w-64 border-l overflow-y-auto p-2 text-xs shrink-0"
          style={{ borderColor: TK.border, background: TK.bg }}>
          <DetailPanel sandbox={sandbox} node={selectedNode} />
        </div>
      )}
    </div>
  )
}

// ── Node tree item ──

function NodeTree({ sandbox, node, depth, selectedPath, onSelect }: {
  sandbox: Sandbox
  node: SandboxNode
  depth: number
  selectedPath: string | null
  onSelect: (node: SandboxNode, path: string) => void
}) {
  const [expanded, setExpanded] = useState(depth < 2)
  const hasChildren = node.children.length > 0
  const isDeleted = !!node.data._deleted
  const isSelected = node.path === selectedPath

  const handleClick = useCallback(() => {
    if (hasChildren) setExpanded(v => !v)
    onSelect(node, node.path)
  }, [hasChildren, node, onSelect])

  const typeColor = node.type === 'channel' ? TK.green
    : node.type === 'message' ? TK.accent
    : node.type === 'channels' ? TK.yellow
    : node.type === 'pchat' ? TK.purple
    : TK.dim

  const childNodes = node.children
    .map(p => sandbox.resolve(p))
    .filter(Boolean) as SandboxNode[]

  return (
    <div style={{ opacity: isDeleted ? 0.4 : 1 }}>
      {/* Node header */}
      <div
        className="flex items-center gap-1 py-0.5 cursor-pointer hover:opacity-80 rounded px-1"
        style={{
          paddingLeft: depth * 14,
          background: isSelected ? `${TK.accent}20` : 'transparent',
        }}
        onClick={handleClick}
      >
        {hasChildren ? (
          expanded
            ? <ChevronDown size={11} style={{ color: TK.dim }} />
            : <ChevronRight size={11} style={{ color: TK.dim }} />
        ) : (
          <span style={{ width: 11 }} />
        )}

        {hasChildren ? (
          expanded
            ? <FolderOpen size={11} style={{ color: TK.yellow }} />
            : <Folder size={11} style={{ color: TK.yellow }} />
        ) : (
          <FileText size={11} style={{ color: TK.dim }} />
        )}

        <span className="truncate" style={{ color: TK.text, fontWeight: depth < 2 ? 600 : 400 }}>
          {node.name}
        </span>

        {node.type && (
          <span className="text-[8px] px-1 rounded shrink-0"
            style={{ color: typeColor, background: `${typeColor}15` }}>
            {node.type}
          </span>
        )}

        {hasChildren && (
          <span className="text-[8px] shrink-0" style={{ color: TK.dim }}>
            [{node.children.length}]
          </span>
        )}

        {node.exec.length > 0 && (
          <span className="text-[8px] shrink-0" style={{ color: TK.purple }}>
            <Hash size={7} className="inline" />{node.exec.length}
          </span>
        )}
      </div>

      {/* Children */}
      {expanded && childNodes.map(child => (
        <NodeTree
          key={child.path}
          sandbox={sandbox}
          node={child}
          depth={depth + 1}
          selectedPath={selectedPath}
          onSelect={onSelect}
        />
      ))}
    </div>
  )
}

// ── Detail panel ──

function DetailPanel({ sandbox, node }: { sandbox: Sandbox; node: SandboxNode }) {
  const [showMeta, setShowMeta] = useState(true)
  const [showData, setShowData] = useState(true)
  const [showExec, setShowExec] = useState(false)

  const dataKeys = Object.keys(node.data).filter(k => k !== '_deleted')
  const execEntries = node.exec
    .map(id => sandbox.getEntry(id))
    .filter(Boolean)

  return (
    <div>
      {/* Path header */}
      <div className="mb-2">
        <div className="text-[9px] uppercase mb-0.5" style={{ color: TK.dim }}>path</div>
        <div className="text-[10px] break-all" style={{ color: TK.accent }}>{node.path}</div>
      </div>

      {node.type && (
        <div className="mb-2">
          <div className="text-[9px] uppercase mb-0.5" style={{ color: TK.dim }}>type</div>
          <div className="text-[10px]" style={{ color: TK.green }}>{node.type}</div>
        </div>
      )}

      {/* Meta section */}
      {Object.keys(node.meta).length > 0 && (
        <Section
          label="_meta"
          color={TK.dim}
          open={showMeta}
          onToggle={() => setShowMeta(v => !v)}
        >
          <JsonBlock data={node.meta} />
        </Section>
      )}

      {/* Data section */}
      {dataKeys.length > 0 && (
        <Section
          label="_data"
          color={TK.dim}
          open={showData}
          onToggle={() => setShowData(v => !v)}
        >
          <JsonBlock data={Object.fromEntries(
            Object.entries(node.data).filter(([k]) => k !== '_deleted')
          )} />
        </Section>
      )}

      {/* Exec section */}
      {node.exec.length > 0 && (
        <Section
          label={`_exec [${node.exec.length}]`}
          color={TK.purple}
          open={showExec}
          onToggle={() => setShowExec(v => !v)}
        >
          {execEntries.map((e, i) => (
            <div key={i} className="py-0.5 border-b" style={{ borderColor: `${TK.border}50` }}>
              <div className="flex items-center gap-1">
                <span style={{ color: TK.accent }}>{e!.op}</span>
                <span style={{ color: TK.dim }}>
                  {new Date(e!.ts).toLocaleTimeString()}
                </span>
                <span style={{ color: TK.green }}>{e!.user}</span>
              </div>
              {e!.result && (
                <pre className="text-[9px] mt-0.5 whitespace-pre-wrap" style={{ color: TK.dim }}>
                  {JSON.stringify(e!.result, null, 1)}
                </pre>
              )}
            </div>
          ))}
        </Section>
      )}

      {/* Children list */}
      {node.children.length > 0 && (
        <Section
          label={`children [${node.children.length}]`}
          color={TK.yellow}
          open={false}
          onToggle={() => {}}
        >
          {node.children.map(p => {
            const child = sandbox.resolve(p)
            return (
              <div key={p} className="text-[9px] py-0.5 flex items-center gap-1">
                <Eye size={8} style={{ color: TK.dim }} />
                <span style={{ color: TK.text }}>{child?.name ?? p}</span>
                {child?.type && (
                  <span style={{ color: TK.dim }}>({child.type})</span>
                )}
              </div>
            )
          })}
        </Section>
      )}

      {/* Deleted marker */}
      {node.data._deleted && (
        <div className="mt-2 text-[9px] px-2 py-1 rounded"
          style={{ background: `${TK.red}20`, color: TK.red }}>
          DELETED (soft)
        </div>
      )}
    </div>
  )
}

// ── Shared components ──

function Section({ label, color, open, onToggle, children }: {
  label: string; color: string; open: boolean
  onToggle: () => void; children: React.ReactNode
}) {
  const [isOpen, setIsOpen] = useState(open)
  const handleToggle = () => { setIsOpen(v => !v); onToggle() }

  return (
    <div className="mb-2">
      <button
        onClick={handleToggle}
        className="text-[9px] py-0.5 hover:opacity-80 flex items-center gap-1"
        style={{ color }}
      >
        {isOpen ? '▾' : '▸'} {label}
      </button>
      {isOpen && (
        <div className="mt-0.5 pl-2">{children}</div>
      )}
    </div>
  )
}

function JsonBlock({ data }: { data: unknown }) {
  return (
    <pre className="text-[9px] p-1.5 rounded whitespace-pre-wrap break-all leading-relaxed"
      style={{ background: TK.bg, color: TK.text }}>
      {JSON.stringify(data, null, 2)}
    </pre>
  )
}
