<script setup lang="ts">
import { RouterLink, RouterView, useRoute } from 'vue-router'
import { computed } from 'vue'
import { moduleEntries } from './router'

const route = useRoute()
const isHome = computed(() => route.name === 'home')
</script>

<template>
  <nav class="top-nav">
    <RouterLink to="/" class="nav-home">Module Hub</RouterLink>
    <span class="divider" v-if="!isHome">›</span>
    <span v-if="!isHome" class="current">
      {{ moduleEntries.find((m) => m.name === route.name)?.title ?? route.name }}
    </span>
    <div class="spacer" />
    <div class="module-links" v-if="!isHome">
      <template v-for="m in moduleEntries" :key="m.name">
        <RouterLink
          v-if="!m.external && m.path"
          :to="m.path"
          class="module-link"
          :class="{ active: route.name === m.name }"
        >
          {{ m.title }}
        </RouterLink>
        <a
          v-else-if="m.external"
          :href="m.external"
          class="module-link external"
        >
          {{ m.title }} ↗
        </a>
      </template>
    </div>
  </nav>

  <main>
    <RouterView />
  </main>
</template>

<style scoped>
.top-nav {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 20px;
  background: #0f0f14;
  border-bottom: 1px solid #403d52;
  font-size: 14px;
}

.nav-home {
  color: #9ccfd8;
  text-decoration: none;
  font-weight: 600;
}

.nav-home:hover {
  color: #c4a7e7;
}

.divider {
  color: #6e6a86;
}

.current {
  color: #e0def4;
}

.spacer {
  flex: 1;
}

.module-links {
  display: flex;
  gap: 6px;
}

.module-link {
  color: #6e6a86;
  text-decoration: none;
  padding: 4px 8px;
  border-radius: 3px;
  font-size: 12px;
}

.module-link.active {
  color: #c4a7e7;
  background: #2a2a33;
}

.module-link:hover {
  color: #9ccfd8;
}

main {
  padding: 16px 0;
}
</style>
