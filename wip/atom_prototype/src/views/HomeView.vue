<script setup lang="ts">
import { RouterLink } from 'vue-router'
import { moduleEntries } from '../router'
</script>

<template>
  <div class="container">
    <h1>Module Hub</h1>
    <p class="subtitle">
      All TS modules served on one port (5177). Pick a module to open it, or click "Home" in the nav
      to return here.
    </p>

    <div class="module-grid">
      <template v-for="entry in moduleEntries" :key="entry.name">
        <!-- Internal: router link. External: plain <a> triggering proxy. -->
        <RouterLink
          v-if="!entry.external && entry.path"
          :to="entry.path"
          class="module-card"
        >
          <h2>{{ entry.title }}</h2>
          <p>{{ entry.description }}</p>
          <div v-if="entry.tags" class="tags">
            <span v-for="tag in entry.tags" :key="tag" class="tag">#{{ tag }}</span>
            <span class="tag origin-tag internal">internal</span>
          </div>
        </RouterLink>
        <a
          v-else-if="entry.external"
          :href="entry.external"
          class="module-card"
        >
          <h2>{{ entry.title }}</h2>
          <p>{{ entry.description }}</p>
          <div v-if="entry.tags" class="tags">
            <span v-for="tag in entry.tags" :key="tag" class="tag">#{{ tag }}</span>
            <span class="tag origin-tag external">external · proxied</span>
          </div>
        </a>
      </template>
    </div>

    <div class="empty-hint" v-if="moduleEntries.length === 0">
      No modules registered yet. Add entries to <code>src/router.ts</code>.
    </div>

    <footer>
      <p><strong>Adding a module — two shapes:</strong></p>
      <p>
        <strong>Internal</strong> (lives in this app): create
        <code>src/views/&lt;Name&gt;View.vue</code>, add route in
        <code>src/router.ts</code>, append <code>ModuleEntry</code> without
        <code>external</code>.
      </p>
      <p>
        <strong>External</strong> (own dev server, any stack): start its server
        on a free port, add proxy rule in <code>vite.config.ts</code>
        (<code>/proxy/&lt;name&gt;</code> → target), append
        <code>ModuleEntry</code> with <code>external: '/proxy/&lt;name&gt;/'</code>.
      </p>
      <p>
        Either way, this landing page and the top nav update automatically.
        External modules look identical from the outside — same port, same URL
        namespace, just proxied.
      </p>
    </footer>
  </div>
</template>

<style scoped>
.module-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 12px;
  margin-top: 16px;
}

.module-card {
  display: block;
  text-decoration: none;
  color: inherit;
  background: #2a2a33;
  border: 1px solid #403d52;
  border-radius: 6px;
  padding: 14px;
  transition: border-color 0.15s;
}

.module-card:hover {
  border-color: #9ccfd8;
}

.module-card h2 {
  margin: 0 0 6px 0;
  color: #c4a7e7;
  font-size: 1.1em;
}

.module-card p {
  margin: 0 0 8px 0;
  font-size: 13px;
  color: #e0def4;
  line-height: 1.4;
}

.tags {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.tag {
  font-size: 11px;
  color: #6e6a86;
}

.origin-tag.internal {
  color: #8ec07c;
}

.origin-tag.external {
  color: #f6c177;
}

.empty-hint {
  color: #6e6a86;
  padding: 14px;
  border: 1px dashed #403d52;
  border-radius: 6px;
}

footer {
  margin-top: 32px;
  color: #6e6a86;
  font-size: 12px;
  line-height: 1.5;
}

code {
  background: #0f0f14;
  padding: 2px 6px;
  border-radius: 3px;
  color: #f6c177;
}
</style>
