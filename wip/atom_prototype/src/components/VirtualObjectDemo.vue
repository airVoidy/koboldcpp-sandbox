<script setup lang="ts">
/**
 * Demonstrates a **projection** from atom state into Vite virtual-module space.
 *
 * Important framing: Vite virtual modules and our Virtual Objects share a
 * structural pattern (name → generated payload) but operate at **different
 * scopes**:
 *
 *   - Our Virtual Objects are pure assembly primitives. Runtime-operational,
 *     atomic, lightweight. Op runs produce dynamic outputs; lifecycle is
 *     tied to registry, not modules.
 *
 *   - Vite virtual modules are build/dev-time module-space artifacts. The
 *     plugin's load() returns immutable content; the module is frozen after
 *     generation (re-generated on HMR invalidation).
 *
 * The relationship is a one-way projection:
 *     atom state  →  projected as Vite virtual module (for importable access)
 *
 * Vite does not know about atoms; we inject the projection through the plugin.
 * The atom's own lifecycle remains independent. Writing our assembly layer
 * fresh is still required — Vite virtual modules are one useful *lens*, not
 * the substrate.
 *
 * This import below is resolved by the atom-snapshot plugin in vite.config.ts:
 *   - resolveId('virtual:atom-snapshot') = \0virtual:atom-snapshot
 *   - load('\0virtual:atom-snapshot')    = generated JSON-as-module
 */
import snapshot from 'virtual:atom-snapshot'
</script>

<template>
  <details class="virtual">
    <summary>Virtual module demo — `virtual:atom-snapshot` (≡ our Virtual Object)</summary>
    <pre>{{ JSON.stringify(snapshot, null, 2) }}</pre>
  </details>
</template>
