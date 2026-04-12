import { useState } from 'react'
import { Hash, Plus } from 'lucide-react'
import type { ChatItem } from '@/types/chat'

interface Props {
  channels: ChatItem[]
  active: string | null
  onSelect: (name: string) => void
  onCreate: (name: string) => void
}

export function ChannelSidebar({ channels, active, onSelect, onCreate }: Props) {
  const [newName, setNewName] = useState('')

  const handleCreate = () => {
    const name = newName.trim()
    if (!name) return
    onCreate(name)
    setNewName('')
  }

  return (
    <aside className="w-56 shrink-0 border-r border-[var(--border)] bg-[var(--surface)] flex flex-col">
      <div className="p-3 border-b border-[var(--border)] text-xs font-semibold text-[var(--text-dim)] uppercase tracking-wider">
        Channels
      </div>

      <div className="flex-1 overflow-y-auto">
        {channels.map(ch => {
          const name = ch.meta?.name ?? ch.name
          const isActive = name === active
          return (
            <button
              key={ch.path}
              onClick={() => onSelect(name)}
              className={`w-full text-left px-3 py-1.5 flex items-center gap-2 text-sm hover:bg-[var(--surface2)] transition-colors ${
                isActive ? 'bg-[var(--surface2)] text-[var(--accent)]' : 'text-[var(--text-dim)]'
              }`}
            >
              <Hash className="w-3.5 h-3.5 shrink-0" />
              {name}
            </button>
          )
        })}
      </div>

      <div className="p-2 border-t border-[var(--border)] flex gap-1">
        <input
          value={newName}
          onChange={e => setNewName(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && handleCreate()}
          placeholder="new channel"
          className="flex-1 bg-[var(--bg)] border border-[var(--border)] rounded px-2 py-1 text-xs text-[var(--text)] placeholder:text-[var(--text-dim)] outline-none focus:border-[var(--accent)]"
        />
        <button
          onClick={handleCreate}
          className="p-1 text-[var(--text-dim)] hover:text-[var(--accent)] transition-colors"
        >
          <Plus className="w-4 h-4" />
        </button>
      </div>
    </aside>
  )
}
