import { useState } from 'react'
import { Send } from 'lucide-react'

interface Props {
  onSend: (text: string) => void
  disabled?: boolean
  channel: string | null
}

export function MessageInput({ onSend, disabled, channel }: Props) {
  const [text, setText] = useState('')

  const handleSend = () => {
    if (!text.trim() || disabled) return
    onSend(text.trim())
    setText('')
  }

  return (
    <div className="border-t border-[var(--border)] px-4 py-2 flex gap-2 items-end">
      <textarea
        value={text}
        onChange={e => setText(e.target.value)}
        onKeyDown={e => {
          if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault()
            handleSend()
          }
        }}
        placeholder={channel ? `Message #${channel}` : 'Select a channel...'}
        disabled={!channel || disabled}
        rows={1}
        className="flex-1 bg-[var(--surface)] border border-[var(--border)] rounded-lg px-3 py-2 text-sm text-[var(--text)] placeholder:text-[var(--text-dim)] outline-none resize-none focus:border-[var(--accent)] disabled:opacity-50 min-h-[36px] max-h-[120px]"
      />
      <button
        onClick={handleSend}
        disabled={!text.trim() || disabled || !channel}
        className="p-2 rounded-lg bg-[var(--accent)] text-white disabled:opacity-30 hover:opacity-90 transition-opacity"
      >
        <Send className="w-4 h-4" />
      </button>
    </div>
  )
}
