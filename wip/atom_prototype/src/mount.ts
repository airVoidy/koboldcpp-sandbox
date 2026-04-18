/**
 * Mount layer — cross-type glue between atom outputs and live container instances.
 *
 * Flow:
 *   atom.run() → returns ContainerSpec → auto-mount wrapper detects shape →
 *   calls mountManager.spawn(spec) → container registry looks up factory by
 *   spec.type → Vue component mounts into a floating cell → live instance
 *   visible on the page.
 *
 * Cross-type bridging = a wrapper that transforms one type of spec into
 * another BEFORE the auto-mount wrapper sees it. Example: bash-exec atom
 * returns { stdout }; wrapper `bashToLexical` transforms that into
 * { type: 'lexical', props: { content: stdout } }; then the spec flows
 * through auto-mount.
 */

import { reactive, type Component } from 'vue'
import type { AtomWrapper, WrapperContext } from './atom'

/** Spec describing a container to spawn. Atom op or wrapper produces this. */
export interface ContainerSpec {
  /** Matches a key in containerRegistry. */
  type: string
  /** Stable id — used for de-dup, update, close. */
  id: string
  /** Human label shown on the floating cell header. */
  title?: string
  /** Props passed into the mounted component. */
  props?: Record<string, unknown>
}

/** Minimum shape needed for a mounted cell. */
export interface Mounted {
  id: string
  type: string
  title: string
  component: Component
  props: Record<string, unknown>
  x: number
  y: number
  w: number
  h: number
  z: number
}

export function isContainerSpec(x: unknown): x is ContainerSpec {
  return (
    typeof x === 'object' &&
    x !== null &&
    typeof (x as ContainerSpec).type === 'string' &&
    typeof (x as ContainerSpec).id === 'string'
  )
}

/** Registry — factory per container type. Register at app boot. */
const registry = new Map<string, { component: Component; defaultTitle: string }>()

export function registerContainer(type: string, component: Component, defaultTitle = type) {
  registry.set(type, { component, defaultTitle })
}

export function hasContainerType(type: string) {
  return registry.has(type)
}

/**
 * Mount manager — reactive list of live container cells. One instance per app
 * (singleton). Views subscribe to `mounted` array to render cells.
 */
class MountManager {
  private zCounter = 10
  private offsetSeed = 0
  mounted = reactive<Mounted[]>([])

  spawn(spec: ContainerSpec): Mounted | null {
    const entry = registry.get(spec.type)
    if (!entry) {
      console.warn(`[mount] unknown container type "${spec.type}"`)
      return null
    }
    // Re-use existing cell if id matches — update props in place.
    const existing = this.mounted.find((m) => m.id === spec.id)
    if (existing) {
      existing.props = { ...(spec.props ?? {}) }
      if (spec.title) existing.title = spec.title
      existing.z = ++this.zCounter
      return existing
    }
    const offset = this.offsetSeed
    this.offsetSeed = (this.offsetSeed + 28) % 200
    const m: Mounted = {
      id: spec.id,
      type: spec.type,
      title: spec.title ?? entry.defaultTitle,
      component: entry.component,
      props: spec.props ?? {},
      x: 40 + offset,
      y: 40 + offset,
      w: 520,
      h: 320,
      z: ++this.zCounter,
    }
    this.mounted.push(m)
    return m
  }

  close(id: string) {
    const i = this.mounted.findIndex((m) => m.id === id)
    if (i >= 0) this.mounted.splice(i, 1)
  }

  focus(id: string) {
    const m = this.mounted.find((x) => x.id === id)
    if (m) m.z = ++this.zCounter
  }

  clear() {
    this.mounted.splice(0, this.mounted.length)
  }
}

export const mountManager = new MountManager()

/**
 * Wrapper: if atom output is a ContainerSpec, spawn/update the container.
 * Pass-through otherwise. Attach with registry.registerWrapper(autoMount()).
 */
export function autoMountWrapper(id = 'auto-mount'): AtomWrapper {
  return {
    id,
    wraps: '*',
    fn: async (ctx: WrapperContext, next) => {
      const out = await next()
      if (isContainerSpec(out)) {
        const mounted = mountManager.spawn(out)
        ctx.trace('spawn', { id: out.id, type: out.type, mounted: mounted != null })
      }
      return out
    },
  }
}

/**
 * Wrapper factory: cross-type transform. Given a target atom id and a
 * transform function, intercepts that atom's output and coerces shape.
 *
 * Example:
 *   bridge('bash-exec', (o) => ({
 *     type: 'lexical',
 *     id: 'bash-out',
 *     props: { content: String((o as any).stdout ?? '') },
 *   }))
 *
 * Chain position matters — put BEFORE auto-mount so the mounter sees the
 * transformed spec.
 */
export function bridgeWrapper(
  id: string,
  wrapsAtomId: string,
  transform: (output: unknown, ctx: WrapperContext) => ContainerSpec | unknown,
): AtomWrapper {
  return {
    id,
    wraps: wrapsAtomId,
    fn: async (ctx, next) => {
      const out = await next()
      const transformed = transform(out, ctx)
      ctx.trace('bridge', { from: wrapsAtomId, to: isContainerSpec(transformed) ? transformed.type : 'passthrough' })
      return transformed
    },
  }
}
