<script setup lang="ts">
// Onglet « Tentatives » : passages des étudiants sur la station, avec lien vers la relecture de la correction
import { computed, onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import DataTable from 'primevue/datatable'
import Column from 'primevue/column'
import Tag from 'primevue/tag'
import Message from 'primevue/message'
import Button from 'primevue/button'
import { apiService } from '../services/api'
import { errorMessage } from '../services/http'
import type { CaseAttemptRow } from '../types'

const props = defineProps<{ caseId: number }>()

const attempts = ref<CaseAttemptRow[] | null>(null)
const loading = ref(false)
const error = ref<string | null>(null)

/** Lignes du tableau : nom affiché et statut triables comme du texte */
const rows = computed(() => (attempts.value ?? []).map((a) => ({
  ...a,
  student: a.full_name ? `${a.full_name} (${a.username})` : a.username,
  status: statusOf(a).label,
})))

function statusOf(a: CaseAttemptRow): { label: string; severity: 'success' | 'info' | 'warn' | 'secondary' } {
  if (!a.completed_at) return { label: 'En cours', severity: 'secondary' }
  if (a.reviewed) return { label: 'Relue', severity: 'success' }
  if (a.evaluated) return { label: 'Corrigée', severity: 'info' }
  return { label: 'Non corrigée', severity: 'warn' }
}

function parseDate(iso: string): Date {
  return new Date(/[zZ]|[+-]\d\d:?\d\d$/.test(iso) ? iso : `${iso}Z`)
}

function fmtDate(iso: string | null): string {
  if (!iso) return '—'
  return parseDate(iso).toLocaleString('fr-FR', { dateStyle: 'short', timeStyle: 'short' })
}

function fmtScore(score: number | null): string {
  return score == null ? '—' : (Math.round(score * 100) / 100).toLocaleString('fr-FR')
}

async function load() {
  loading.value = true
  error.value = null
  try {
    attempts.value = await apiService.getCaseAttempts(props.caseId)
  } catch (e) {
    error.value = `Impossible de charger les tentatives. ${errorMessage(e)}`
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<template>
  <div class="attempts">
    <div class="attempts-head">
      <h2 id="attempts-title">Tentatives sur cette station</h2>
      <Button label="Actualiser" icon="pi pi-refresh" size="small" text :loading="loading" @click="load" />
    </div>
    <p class="lead">
      Relisez la correction automatique d'un passage : modifiez les points d'un item ou relancez la correction.
    </p>

    <Message v-if="error" severity="error" :closable="false">{{ error }}</Message>
    <p v-else-if="attempts && !attempts.length" class="muted">Aucune tentative pour l'instant.</p>

    <DataTable
      v-if="rows.length"
      :value="rows"
      data-key="attempt_id"
      sort-field="started_at"
      :sort-order="-1"
      removable-sort
      size="small"
      striped-rows
      :table-props="{ 'aria-labelledby': 'attempts-title' }"
    >
      <Column field="student" header="Étudiant" sortable />
      <Column field="is_test" header="Type" sortable>
        <template #body="{ data }">{{ data.is_test ? 'Test enseignant' : 'Étudiant' }}</template>
      </Column>
      <Column field="started_at" header="Début" sortable>
        <template #body="{ data }"><time :datetime="data.started_at">{{ fmtDate(data.started_at) }}</time></template>
      </Column>
      <Column field="completed_at" header="Fin" sortable>
        <template #body="{ data }">{{ fmtDate(data.completed_at) }}</template>
      </Column>
      <Column field="score_20" header="Note /20" sortable>
        <template #body="{ data }">{{ fmtScore(data.score_20) }}</template>
      </Column>
      <Column field="status" header="Statut" sortable>
        <template #body="{ data }">
          <Tag :value="statusOf(data).label" :severity="statusOf(data).severity" />
        </template>
      </Column>
      <Column header="Action">
        <template #body="{ data }">
          <RouterLink
            :to="{ name: 'attempt-review', params: { attemptId: data.attempt_id } }"
            :aria-label="`Relire la tentative de ${data.student} du ${fmtDate(data.started_at)}`"
          >Relire</RouterLink>
        </template>
      </Column>
    </DataTable>
  </div>
</template>

<style scoped>
.attempts { display: flex; flex-direction: column; gap: 0.75rem; }
.attempts-head { display: flex; justify-content: space-between; align-items: center; gap: 0.5rem; flex-wrap: wrap; }
.attempts-head h2 { margin: 0; font-size: 1.1rem; }
.lead { color: #475569; font-size: 0.92rem; margin: 0; }
.muted { color: #475569; }
</style>
