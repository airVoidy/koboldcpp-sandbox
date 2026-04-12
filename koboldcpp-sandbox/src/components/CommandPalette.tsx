import { useState, useEffect } from 'react'
import { Command } from 'cmdk'
import { Terminal } from 'lucide-react'
import type { CmdResult } from '@/types/chat'

interface Props {
  open: boolean
  onClose: () => void
  exec: (cmd: string) => Promise<{ result: CmdResult; local: boolean }>
}

export function CommandPalette({ open, onClose, exec }: Props) {
  const [value, setValue] = useState('')
  const [result, setResult] = useState<string | null>(null)

  useEffect(() => {
    if (!open) {
      setValue('')
      setResult(null)
    }
  }, [open])

  const runCmd = async (cmd: string) => {
    try {
      const { result: r, local } = await exec(cmd)
      const display = { ...r, _local: local }
      setResult(JSON.stringify(display, null, 2))
    } catch (e: unknown) {
      setResult(e instanceof Error ? e.message : 'error')
    }
  }

  if (!open) return null

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center pt-[20vh]" onClick={onClose}>
      <div
        className="w-[560px] bg-[var(--surface)] border border-[var(--border)] rounded-xl shadow-2xl overflow-hidden"
        onClick={e => e.stopPropagation()}
      >
        <Command label="Command Palette" shouldFilter={false}>
          <div className="flex items-center gap-2 px-4 py-3 border-b border-[var(--border)]">
            <Terminal className="w-4 h-4 text-[var(--text-dim)]" />
            <Command.Input
              value={value}
              onValueChange={setValue}
              onKeyDown={e => {
                if (e.key === 'Enter' && value.startsWith('/')) {
                  e.preventDefault()
                  runCmd(value)
                }
                if (e.key === 'Escape') onClose()
              }}
              placeholder="Type a /command..."
              className="flex-1 bg-transparent text-sm text-[var(--text)] placeholder:text-[var(--text-dim)] outline-none"
            />
          </div>

          <Command.List className="max-h-[300px] overflow-y-auto p-2">
            {!result && (
              <Command.Group heading="Quick commands" className="text-[10px] text-[var(--text-dim)] uppercase px-2 py-1">
                {['/wiki status', '/wiki list', '/dir', '/cat'].map(cmd => (
                  <Command.Item
                    key={cmd}
                    value={cmd}
                    onSelect={() => { setValue(cmd); runCmd(cmd) }}
                    className="px-3 py-1.5 rounded text-sm cursor-pointer text-[var(--text-dim)] hover:bg-[var(--surface2)] hover:text-[var(--text)] data-[selected=true]:bg-[var(--surface2)]"
                  >
                    {cmd}
                  </Command.Item>
                ))}
              </Command.Group>
            )}

            {result && (
              <pre className="p-3 text-xs text-[var(--text-dim)] whitespace-pre-wrap max-h-[250px] overflow-y-auto">
                {result}
              </pre>
            )}
          </Command.List>
        </Command>
      </div>
    </div>
  )
}
