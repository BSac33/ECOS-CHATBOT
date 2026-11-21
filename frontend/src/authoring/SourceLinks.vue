<script setup lang="ts">
import { computed } from 'vue'
import { safeExternalUrl, type SourceRef } from './api'

const props = defineProps<{ sources: SourceRef[] }>()
// Seules les adresses http(s) deviennent des liens (jamais javascript:, data:...)
const links = computed(() => props.sources.map((s) => ({ label: s.label, href: safeExternalUrl(s.url) })))
</script>

<template>
  <div v-if="links.length" class="sources">
    <i class="pi pi-book" aria-hidden="true"></i>
    <span class="sr-only">Sources :</span>
    <template v-for="(s, i) in links" :key="i">
      <a v-if="s.href" :href="s.href" target="_blank" rel="noopener noreferrer">{{ s.label }}<span class="sr-only"> (nouvel onglet)</span></a>
      <span v-else>{{ s.label }}</span>
    </template>
  </div>
</template>

<style scoped>
.sources { display: flex; flex-wrap: wrap; gap: 0.25rem 0.75rem; align-items: center; font-size: 0.8rem; color: #475569; }
.sources a { color: #3730a3; font-weight: 400; }
</style>
