<script setup lang="ts">
import type { SourceRef } from './api'
defineProps<{ sources: SourceRef[] }>()
</script>

<template>
  <div v-if="sources.length" class="sources">
    <i class="pi pi-book" aria-hidden="true"></i>
    <template v-for="(s, i) in sources" :key="i">
      <a v-if="s.url" :href="s.url" target="_blank" rel="noopener">{{ s.label }}</a>
      <span v-else>{{ s.label }}</span>
    </template>
  </div>
</template>

<style scoped>
.sources { display: flex; flex-wrap: wrap; gap: 0.25rem 0.75rem; align-items: center; font-size: 0.8rem; color: #64748b; }
.sources a { color: #4f46e5; font-weight: 400; }
</style>
