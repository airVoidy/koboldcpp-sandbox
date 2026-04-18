/**
 * Stub worker for future synckit bridging experiments.
 *
 * In node environments synckit's runAsWorker provides Atomics-based blocking
 * sync bridge. In browser web-workers it's more complex. For this prototype
 * the worker is present but not yet wired; see README "Next iterations".
 *
 * Uncomment once we commit to a browser synckit approach (or swap for a plain
 * SharedArrayBuffer + Atomics.wait hand-rolled pattern).
 */

// import { runAsWorker } from 'synckit'
// runAsWorker(async (input: unknown) => {
//   // Example: remote projection resolution
//   return { echoed: input, at: Date.now() }
// })

export {}
