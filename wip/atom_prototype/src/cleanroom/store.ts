// Re-export of the canonical clean-room bootstrap from wip/atomic_cleanroom_bootstrap.ts.
// This indirection keeps the import path stable inside src/cleanroom/* and lets
// vitest pick up tests without altering the standalone reference file.
//
// See:
//   - docs/ATOMIC_CLEANROOM_BOOTSTRAP_V0_1.md
//   - docs/ATOMIC_PROJECTION_SLOT_SPEC_V0_1.md
//   - docs/ATOMIC_AABB_LIST_LAYOUT_V0_1.md
export * from '../../../atomic_cleanroom_bootstrap'
