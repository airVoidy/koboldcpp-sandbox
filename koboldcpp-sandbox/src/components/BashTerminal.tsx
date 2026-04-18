/**
 * BashTerminal — xterm frontend wired to just-bash.
 *
 * We use just-bash directly (not bash-tool) because bash-tool is Node-first
 * and its skill-tool entry chokes on browser bundling. just-bash ships a
 * clean browser build with InMemoryFs / MountableFs / OverlayFs.
 *
 * The "middlelayer" hook is applied manually around each command:
 *   before → optional batching / validation / logging
 *   exec   → bash.exec(cmd) in the in-memory VFS
 *   after  → middlelayer.exec() stub records the call in Store's exec log
 *             via the shadow-metadata writer (see runtime/middlelayer.ts)
 *
 * We don't re-send the shell command to the server — it runs locally in the
 * browser VFS. The "noop" server notification is optional and disabled by
 * default to keep the terminal purely client-side.
 */
import { useEffect, useRef } from 'react'
import { Terminal as Xterm } from '@xterm/xterm'
import { FitAddon } from '@xterm/addon-fit'
import { WebLinksAddon } from '@xterm/addon-web-links'
import '@xterm/xterm/css/xterm.css'
import { Bash, InMemoryFs } from 'just-bash'
import { getMiddlelayer } from '@/runtime/middlelayer'

export interface BashTerminalProps {
  /** Prompt string to show (default "$ "). */
  prompt?: string
  /** Requester id used for middlelayer provenance (default "shell"). */
  requester?: string
  /** If true, also echo commands to the middlelayer log (default true). */
  recordToMiddlelayer?: boolean
}

export function BashTerminal({
  prompt = '$ ',
  requester = 'shell',
  recordToMiddlelayer = true,
}: BashTerminalProps) {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const termRef = useRef<Xterm | null>(null)
  const bufferRef = useRef('')
  const historyRef = useRef<string[]>([])
  const historyIdxRef = useRef<number>(-1)

  useEffect(() => {
    if (!containerRef.current) return

    const term = new Xterm({
      fontFamily: '"JetBrains Mono", Menlo, monospace',
      fontSize: 13,
      theme: {
        background: '#1a1a2e',
        foreground: '#e0e0f0',
        cursor: '#6c63ff',
        red: '#ff5566',
        green: '#44dd88',
        yellow: '#ffcc66',
        blue: '#66ccff',
        magenta: '#c084fc',
        cyan: '#66ccff',
      },
      cursorBlink: true,
      convertEol: true,
    })
    const fit = new FitAddon()
    term.loadAddon(fit)
    term.loadAddon(new WebLinksAddon())
    term.open(containerRef.current)
    queueMicrotask(() => fit.fit())
    termRef.current = term

    // Create bash instance with isolated in-memory FS
    const fs = new InMemoryFs()
    const bash = new Bash({ fs })
    const middlelayer = getMiddlelayer()

    term.writeln('\x1b[32mjust-bash ready\x1b[0m — try: ls, mkdir, echo, cat, pwd')
    term.write(`\r\n${prompt}`)

    async function runCommand(cmd: string): Promise<void> {
      try {
        const res = await bash.exec(cmd)
        if (res.stdout) term.write(res.stdout.replace(/\n/g, '\r\n'))
        if (res.stderr) term.write(`\x1b[31m${res.stderr.replace(/\n/g, '\r\n')}\x1b[0m`)
        if (res.exitCode !== 0) {
          term.write(`\x1b[33m[exit ${res.exitCode}]\x1b[0m\r\n`)
        }
        // Record to middlelayer audit log (doesn't re-execute on server)
        if (recordToMiddlelayer) {
          middlelayer
            .exec({
              cmd: `__shell ${JSON.stringify({ cmd, exit: res.exitCode })}`,
              requester,
              ts: new Date().toISOString(),
              // Empty expected targets — shell cmds don't mutate Store by default
            })
            .catch(() => {})
        }
      } catch (err) {
        term.write(`\x1b[31m${String(err)}\x1b[0m\r\n`)
      } finally {
        term.write(`\r\n${prompt}`)
      }
    }

    const onData = term.onData((data) => {
      for (const ch of data) {
        const code = ch.charCodeAt(0)
        // Enter
        if (code === 13) {
          term.writeln('')
          const cmd = bufferRef.current.trim()
          bufferRef.current = ''
          if (cmd) {
            historyRef.current.push(cmd)
            historyIdxRef.current = historyRef.current.length
            void runCommand(cmd)
          } else {
            term.write(prompt)
          }
        }
        // Backspace
        else if (code === 127) {
          if (bufferRef.current.length > 0) {
            bufferRef.current = bufferRef.current.slice(0, -1)
            term.write('\b \b')
          }
        }
        // Ctrl+C
        else if (code === 3) {
          term.writeln('^C')
          bufferRef.current = ''
          term.write(prompt)
        }
        // Printable
        else if (code >= 32 && code !== 127) {
          bufferRef.current += ch
          term.write(ch)
        }
      }
    })

    const resizeObs = new ResizeObserver(() => {
      try { fit.fit() } catch {}
    })
    resizeObs.observe(containerRef.current)

    return () => {
      onData.dispose()
      resizeObs.disconnect()
      term.dispose()
    }
  }, [prompt, requester, recordToMiddlelayer])

  return (
    <div
      ref={containerRef}
      className="h-full w-full overflow-hidden"
      style={{ background: '#1a1a2e', padding: 4 }}
    />
  )
}
