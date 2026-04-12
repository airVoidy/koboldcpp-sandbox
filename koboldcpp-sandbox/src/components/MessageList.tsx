import { useRef, useEffect } from 'react'
import { ThumbsUp } from 'lucide-react'
import type { ChatItem } from '@/types/chat'

interface Props {
  messages: ChatItem[]
  user: string
  onReact: (msgId: string, emoji: string) => void
}

function Reactions({ reactions, user, msgId, onReact }: {
  reactions: Record<string, { users: string[]; count: number }>
  user: string
  msgId: string
  onReact: (msgId: string, emoji: string) => void
}) {
  const entries = Object.entries(reactions)
  if (!entries.length) return null

  return (
    <div className="flex gap-1 mt-1.5 flex-wrap">
      {entries.map(([emoji, info]) => {
        const isSelf = info.users.includes(user)
        return (
          <button
            key={emoji}
            onClick={() => onReact(msgId, emoji)}
            className={`text-[10px] px-1.5 py-0.5 rounded-full border transition-colors ${
              isSelf
                ? 'border-[var(--accent)] text-[var(--accent)]'
                : 'border-[var(--border)] text-[var(--text-dim)]'
            } hover:border-[var(--accent)] bg-[var(--surface2)]`}
          >
            {emoji} {info.count}
          </button>
        )
      })}
    </div>
  )
}

export function MessageList({ messages, user, onReact }: Props) {
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages.length])

  if (!messages.length) {
    return (
      <div className="flex-1 flex items-center justify-center text-[var(--text-dim)] text-sm">
        No messages yet. Say something!
      </div>
    )
  }

  return (
    <div className="flex-1 overflow-y-auto px-4 py-2 space-y-1">
      {messages.map(msg => {
        const isSelf = msg.meta.user === user
        const time = msg.meta.ts ? new Date(msg.meta.ts).toLocaleTimeString() : ''
        const reactions = msg.data?.reactions ?? {}

        return (
          <div
            key={msg.path}
            className={`group py-1.5 ${isSelf ? 'text-right' : ''}`}
          >
            <div className="inline-block text-left max-w-[80%]">
              <div className="flex items-baseline gap-2 text-[10px]">
                <span className="font-semibold text-[var(--green)]">{msg.meta.user ?? 'anon'}</span>
                <span className="text-[var(--text-dim)]">{time}</span>
              </div>
              <div className="text-sm mt-0.5">{msg.data?.content ?? ''}</div>
              <Reactions reactions={reactions} user={user} msgId={msg.name} onReact={onReact} />
              <div className="opacity-0 group-hover:opacity-100 transition-opacity mt-1">
                <button
                  onClick={() => onReact(msg.name, 'thumbsup')}
                  className="text-[10px] p-0.5 text-[var(--text-dim)] hover:text-[var(--accent)]"
                >
                  <ThumbsUp className="w-3 h-3" />
                </button>
              </div>
            </div>
          </div>
        )
      })}
      <div ref={bottomRef} />
    </div>
  )
}
