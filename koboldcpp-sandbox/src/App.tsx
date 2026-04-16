import { useState, useEffect } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ChannelSidebar } from '@/components/ChannelSidebar'
import { MessageList } from '@/components/MessageList'
import { MessageInput } from '@/components/MessageInput'
import { DebugConsole } from '@/components/DebugConsole'
import { useChat } from '@/hooks/useChat'
import { Bug, Loader2, Terminal } from 'lucide-react'

const queryClient = new QueryClient()

function Chat() {
  const {
    state,
    channels, messages, activeChannel,
    user, setUser,
    loading, error,
    selectChannel, postMessage, createChannel, toggleReaction,
    refresh,
    exec,
  } = useChat()

  const [debugOpen, setDebugOpen] = useState(false)
  const [debugInitialTab, setDebugInitialTab] = useState<string | undefined>(undefined)

  // Ctrl+K opens debug console with Shell tab, Ctrl+Shift+D toggles debug console
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
        e.preventDefault()
        if (!debugOpen) {
          setDebugInitialTab('shell')
          setDebugOpen(true)
        } else {
          // already open: switch to shell tab
          setDebugInitialTab('shell')
        }
      }
      if ((e.ctrlKey || e.metaKey) && e.shiftKey && e.key === 'D') {
        e.preventDefault()
        setDebugOpen(v => !v)
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [debugOpen])

  return (
    <div className="flex h-screen">
      <ChannelSidebar
        channels={channels}
        active={activeChannel}
        onSelect={selectChannel}
        onCreate={createChannel}
      />

      <main className="flex-1 flex flex-col min-w-0">
        {/* Top bar */}
        <header className="h-10 border-b border-[var(--border)] px-4 flex items-center justify-between shrink-0">
          <div className="flex items-center gap-2">
            {activeChannel && (
              <span className="text-sm font-semibold text-[var(--text)]">
                # {activeChannel}
              </span>
            )}
            {loading && <Loader2 className="w-3 h-3 animate-spin text-[var(--text-dim)]" />}
            {error && <span className="text-xs text-[var(--red)]">{error}</span>}
          </div>

          <div className="flex items-center gap-3">
            <input
              value={user}
              onChange={e => setUser(e.target.value)}
              className="w-20 bg-transparent border-b border-[var(--border)] text-xs text-[var(--text-dim)] outline-none text-right"
              placeholder="username"
            />
            <button
              onClick={() => setDebugOpen(v => !v)}
              className="p-1 text-[var(--text-dim)] hover:text-[var(--accent)] transition-colors"
              title="Ctrl+Shift+D"
            >
              <Bug className="w-4 h-4" />
            </button>
            <button
              onClick={() => { setDebugInitialTab('shell'); setDebugOpen(true) }}
              className="p-1 text-[var(--text-dim)] hover:text-[var(--accent)] transition-colors"
              title="Ctrl+K"
            >
              <Terminal className="w-4 h-4" />
            </button>
          </div>
        </header>

        {/* Messages */}
        <MessageList messages={messages} user={user} onReact={toggleReaction} />

        {/* Input */}
        <MessageInput
          onSend={postMessage}
          disabled={loading}
          channel={activeChannel}
        />
      </main>

      <DebugConsole
        visible={debugOpen}
        onClose={() => setDebugOpen(false)}
        chatState={state}
        user={user}
        exec={exec}
        initialTab={debugInitialTab}
      />
    </div>
  )
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <Chat />
    </QueryClientProvider>
  )
}
