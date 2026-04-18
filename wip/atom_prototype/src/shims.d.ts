declare module '*.vue' {
  import type { DefineComponent } from 'vue'
  const component: DefineComponent<{}, {}, any>
  export default component
}

declare module 'virtual:atom-snapshot' {
  export interface AtomSnapshot {
    generatedAt: number
    atomIds: string[]
    values: Record<string, unknown>
  }
  const snapshot: AtomSnapshot
  export default snapshot
}
