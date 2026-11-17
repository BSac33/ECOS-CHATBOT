<script setup lang="ts">
// Atelier : les stations de l'enseignant
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import Button from 'primevue/button'
import InputText from 'primevue/inputtext'
import Message from 'primevue/message'
import Tag from 'primevue/tag'
import { authoringApi, type CaseSummary } from './api'

const router = useRouter()
const cases = ref<CaseSummary[] | null>(null)
const error = ref('')
const newTitle = ref('')
const creating = ref(false)

onMounted(async () => {
  try {
    cases.value = await authoringApi.listCases()
  } catch (e: any) {
    error.value = e.message
  }
})

async function create() {
  creating.value = true
  try {
    const detail = await authoringApi.createCase(newTitle.value)
    router.push({ name: 'case-editor', params: { caseId: detail.id } })
  } catch (e: any) {
    error.value = e.message
  } finally {
    creating.value = false
  }
}
</script>

<template>
  <div class="authoring-page">
    <h1>Atelier de création de stations</h1>
    <p class="lead">
      Décrivez le patient et ce qu'il sait ; la plateforme en tire le jeu du patient, la grille et la correction.
      Le bouton « Générer » complète la fiche à partir du référentiel officiel.
    </p>

    <form class="create" @submit.prevent="create">
      <InputText v-model="newTitle" placeholder="Titre de la nouvelle station (ex. « Douleur thoracique aux urgences »)" fluid />
      <Button type="submit" label="Créer" icon="pi pi-plus" :loading="creating" />
    </form>

    <Message v-if="error" severity="error" :closable="false">{{ error }}</Message>

    <p v-if="cases && !cases.length" class="muted">Aucune station pour l'instant.</p>
    <ul v-if="cases?.length" class="cases">
      <li v-for="c in cases" :key="c.id">
        <RouterLink :to="{ name: 'case-editor', params: { caseId: c.id } }" class="case-row">
          <span class="case-title">{{ c.title }}</span>
          <span class="case-meta">
            <Tag :value="c.status === 'published' ? `Publiée · v${c.latest_version}` : 'Brouillon'"
                 :severity="c.status === 'published' ? 'success' : 'secondary'" />
            <Tag v-if="c.errors" :value="`${c.errors} erreur${c.errors > 1 ? 's' : ''}`" severity="danger" />
            <Tag v-else-if="c.warnings" :value="`${c.warnings} à vérifier`" severity="warn" />
          </span>
        </RouterLink>
      </li>
    </ul>
  </div>
</template>

<style scoped>
.authoring-page { height: 100%; overflow-y: auto; padding: 1rem 0 3rem; max-width: 60rem; box-sizing: border-box; }
h1 { font-size: 1.75rem; margin: 0.5rem 0; }
.lead { color: #475569; }
.create { display: flex; gap: 0.5rem; margin: 1.25rem 0; }
.cases { list-style: none; padding: 0; margin: 0; display: flex; flex-direction: column; gap: 0.5rem; }
.case-row {
  display: flex; justify-content: space-between; align-items: center; gap: 1rem; flex-wrap: wrap;
  padding: 0.8rem 1rem; border: 1px solid #e2e8f0; border-radius: 10px; color: #1e293b; font-weight: 500;
}
.case-row:hover { background: #f8fafc; color: #1e293b; }
.case-meta { display: flex; gap: 0.4rem; }
.muted { color: #64748b; }
</style>
