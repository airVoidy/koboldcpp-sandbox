/** Core types matching server _meta.json + _data.json */
import type { Projection } from './runtime'

export interface NodeMeta {
  type: string
  user?: string
  ts?: string
  name?: string
}

export interface NodeData {
  content?: string
  reactions?: Record<string, { users: string[]; count: number }>
  _deleted?: boolean
  [key: string]: unknown
}

export interface ChatItem {
  name: string
  path: string
  meta: NodeMeta
  data: NodeData
  /** Optional L1 projection (when requested) */
  projection?: Projection
}

export interface ChatState {
  channels: ChatItem[]
  messages: ChatItem[]
  active_channel: string | null
  user: string
  ts: string
  source?: string
}

export interface CmdResult {
  ok?: boolean
  error?: string
  [key: string]: unknown
}
