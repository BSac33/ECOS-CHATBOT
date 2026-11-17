<script setup lang="ts">
// Recherche dans le référentiel officiel (items de la station d'abord)
import { ref } from 'vue'
import InputText from 'primevue/inputtext'
import Button from 'primevue/button'
import Tag from 'primevue/tag'
import ToggleSwitch from 'primevue/toggleswitch'
import { authoringApi, type CorpusHit } from './api'

const props = defineProps<{ items: number[] }>()

const query = ref('')
const onlyItems = ref(true)
const hits = ref<CorpusHit[] | null>(null)
const loading = ref(false)
const error = ref('')

async function search() {
  if (!query.value.trim()) return
  loading.value = true
  error.value = ''
  try {
    hits.value = await authoringApi.searchCorpus(query.value, onlyItems.value ? props.items : [])
  } catch (e: any) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="corpus">
    <form class="search" @submit.prevent="search">
      <InputText v-model="query" placeholder="Ex. facteurs de risque, examen physique..." fluid />
      <Button type="submit" icon="pi pi-search" :loading="loading" aria-label="Rechercher" />
    </form>
    <label v-if="items.length" class="toggle">
      <ToggleSwitch v-model="onlyItems" /> Items de la station seulement ({{ items.join(', ') }})
    </label>
    <p v-if="error" class="error">{{ error }}</p>
    <p v-if="hits && !hits.length" class="muted">Aucun extrait trouvé. Le référentiel a-t-il été importé ?</p>
    <article v-for="h in hits || []" :key="h.chunk_id" class="hit">
      <div class="hit-head">
        <Tag v-if="h.rank" :value="`Rang ${h.rank}`" :severity="h.rank === 'A' ? 'success' : 'secondary'" />
        <Tag v-if="h.kind !== 'cours'" :value="h.kind === 'objectif' ? 'Objectif' : h.kind.replace('_', ' ')" severity="info" />
        <a :href="h.url" target="_blank" rel="noopener">{{ h.label }}</a>
      </div>
      <p class="text">{{ h.text }}</p>
    </article>
  </div>
</template>

<style scoped>
.corpus { display: flex; flex-direction: column; gap: 0.6rem; }
.search { display: flex; gap: 0.4rem; }
.toggle { display: flex; align-items: center; gap: 0.5rem; font-size: 0.85rem; color: #475569; }
.hit { border: 1px solid #e2e8f0; border-radius: 10px; padding: 0.6rem 0.75rem; }
.hit-head { display: flex; gap: 0.4rem; align-items: center; flex-wrap: wrap; font-size: 0.85rem; }
.hit-head a { color: #4f46e5; font-weight: 500; }
.text { margin: 0.4rem 0 0; white-space: pre-line; font-size: 0.88rem; color: #334155; max-height: 12rem; overflow: auto; }
.muted { color: #64748b; font-size: 0.9rem; }
.error { color: #b91c1c; }
</style>
