/**
 * Minimal signal primitive.
 *
 * Inlined from the dev.to 5-part reactive-TS series pattern.
 * ~100 LOC: state + event + computed + effect with auto-tracked deps stack.
 *
 * Not a dependency — keeps bundle tiny and gives us full control.
 * ReactiveTS path-listener / batching features added opportunistically later if needed.
 *
 * Usage:
 *   const count = state(0)
 *   count()              // read: 0
 *   count.set(5)         // write
 *   count.subscribe(fn)  // manual subscribe
 *
 *   const doubled = computed(() => count() * 2)   // auto-tracks count
 *   effect(() => console.log(count()))             // re-runs on change
 */

// ── Auto-tracked dependency stack ──

type Tracker = () => void
const trackerStack: Tracker[] = []

/** Runs `fn` with `tracker` registered; auto-tracked reads subscribe to it. */
function autoTrack<T>(tracker: Tracker, fn: () => T): T {
  trackerStack.push(tracker)
  try {
    return fn()
  } finally {
    trackerStack.pop()
  }
}

/** If a tracker is active, subscribe it to the given subscribe function. */
function registerCurrent(subscribe: (fn: () => void) => () => void): void {
  const current = trackerStack[trackerStack.length - 1]
  if (current) subscribe(current)
}

// ── Listeners primitive ──

interface Listeners {
  subscribe(fn: () => void): () => void
  emit(): void
}

function createListeners(): Listeners {
  const subs = new Set<() => void>()
  return {
    subscribe(fn) {
      subs.add(fn)
      return () => subs.delete(fn)
    },
    emit() {
      for (const fn of subs) fn()
    },
  }
}

// ── Signal (state) ──

export interface Signal<T> {
  (): T
  set(value: T): void
  update(fn: (prev: T) => T): void
  subscribe(fn: () => void): () => void
}

/** Mutable reactive value. */
export function state<T>(initial: T): Signal<T> {
  let value = initial
  const listeners = createListeners()

  const getter = (() => {
    registerCurrent(listeners.subscribe)
    return value
  }) as Signal<T>

  getter.set = (next: T) => {
    if (Object.is(next, value)) return
    value = next
    listeners.emit()
  }
  getter.update = (fn) => getter.set(fn(value))
  getter.subscribe = listeners.subscribe

  return getter
}

// ── Computed (derived) ──

export interface Computed<T> {
  (): T
  subscribe(fn: () => void): () => void
}

/** Derived signal — re-evaluates when any tracked dep changes. */
export function computed<T>(compute: () => T): Computed<T> {
  const listeners = createListeners()
  let cached: T
  let dirty = true

  const recompute = () => {
    dirty = true
    listeners.emit()
  }

  const getter = (() => {
    if (dirty) {
      cached = autoTrack(recompute, compute)
      dirty = false
    }
    registerCurrent(listeners.subscribe)
    return cached
  }) as Computed<T>

  getter.subscribe = listeners.subscribe
  return getter
}

// ── Effect (side-effect) ──

/** Runs `fn` immediately and again whenever any tracked dep changes. Returns dispose. */
export function effect(fn: () => void): () => void {
  const unsubs: Array<() => void> = []
  const wrapped = () => {
    // Dispose previous subscriptions
    for (const u of unsubs) u()
    unsubs.length = 0
    autoTrack(wrapped, fn)
  }
  wrapped()
  return () => {
    for (const u of unsubs) u()
    unsubs.length = 0
  }
}

// ── Event (pure dispatcher, no state) ──

export interface Event<T> {
  (): void
  emit(value: T): void
  subscribe(fn: (value: T) => void): () => void
}

/** Pure event dispatcher — no stored value, just fire-and-forget. */
export function event<T = void>(): Event<T> {
  const subs = new Set<(value: T) => void>()
  const dispatcher = (() => {}) as Event<T>
  dispatcher.emit = (value) => {
    for (const fn of subs) fn(value)
  }
  dispatcher.subscribe = (fn) => {
    subs.add(fn)
    return () => subs.delete(fn)
  }
  return dispatcher
}
