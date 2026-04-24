// Clean-room atomic primitives.
//
// Layered on top of the bootstrap (AtomicStore + ProjectionSlot) without
// modifying it. Each module is independent — pick what you need:
//
//   pipeline   — declared → resolving → materialized | shadow | problem
//   aabb       — three-zone list layout (-1 / 0 / +1)
//   portals    — GloryHole (point-to-one) + StreamGate (point-to-many)
//   contracts  — FutureContract + KeyframeUnion + CheckpointSync
//
// Each consumes only the bootstrap's public Store API. They compose freely
// because nothing modifies anything else's state.

export * from './store'
export * from './pipeline'
export * from './aabb'
export * from './portals'
export * from './contracts'
