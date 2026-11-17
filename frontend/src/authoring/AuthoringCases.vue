<script setup lang="ts">
// Atelier : les stations de l'enseignant
import { computed, onMounted, ref } from 'vue'
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
const mine = computed(() => (cases.value || []).filter((c) => c.owned))
const toReview = computed(() => (cases.value || []).filter((c) => !c.owned))

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

    <h2>Mes stations</h2>
    <p v-if="cases && !mine.length" class="muted">Aucune station pour l'instant.</p>
    <ul v-if="mine.length" class="cases">
      <li v-for="c in mine" :key="c.id">
        <RouterLink :to="{ name: 'case-editor', params: { caseId: c.id } }" class="case-row">
          <span class="case-title">{{ c.title }}</span>
          <span class="case-meta">
            <Tag :value="c.status === 'published' ? `Publiée · v${c.latest_version}` : 'Brouillon'"
                 :severity="c.status === 'published' ? 'success' : 'secondary'" />
            <Tag v-if="c.review_status === 'a_relire'" value="À relire" severity="warn" icon="pi pi-eye" />
            <Tag v-else-if="c.review_status === 'relue'" value="Relue" severity="success" icon="pi pi-check" />
            <Tag v-if="c.errors" :value="`${c.errors} erreur${c.errors > 1 ? 's' : ''}`" severity="danger" />
            <Tag v-else-if="c.warnings" :value="`${c.warnings} à vérifier`" severity="warn" />
          </span>
        </RouterLink>
      </li>
    </ul>

    <template v-if="toReview.length">
      <h2>À relire pour mes collègues</h2>
      <p class="muted">Relecture facultative : ces stations peuvent déjà être publiées.</p>
      <ul class="cases">
        <li v-for="c in toReview" :key="c.id">
          <RouterLink :to="{ name: 'case-editor', params: { caseId: c.id } }" class="case-row">
            <span class="case-title">{{ c.title }} <span class="author">· {{ c.author }}</span></span>
            <span class="case-meta">
              <Tag :value="c.status === 'published' ? `Publiée · v${c.latest_version}` : 'Brouillon'"
                   :severity="c.status === 'published' ? 'success' : 'secondary'" />
              <Tag value="À relire" severity="warn" icon="pi pi-eye" />
            </span>
          </RouterLink>
        </li>
      </ul>
    </template>
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
h2 { font-size: 1.15rem; margin: 1.5rem 0 0.6rem; }
.author { color: #64748b; font-weight: 400; }
</style>
