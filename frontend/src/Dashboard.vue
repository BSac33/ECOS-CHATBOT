<script setup lang="ts">
import { onMounted, ref } from 'vue';
import { useRouter } from 'vue-router';
import Card from 'primevue/card';
import Button from 'primevue/button';
import Message from 'primevue/message';
import InstructionPopup from './components/InstructionPopup.vue';
import { useAuthStore } from './stores/auth';
import { apiService } from './services/api';
import { errorMessage as messageOf } from './services/http';
import { STATION_TYPE_LABELS, type CaseInstructions, type ClinicalCase } from './types';

const authStore = useAuthStore();
const router = useRouter();

const caseList = ref<ClinicalCase[]>([]);
const loadingCases = ref(true);
const errorMessage = ref<string | null>(null);

const isVisible = ref(false);
const popupContent = ref<CaseInstructions | null>(null);
const openingCaseId = ref<number | null>(null);
const starting = ref(false);
const startError = ref<string | null>(null);

async function loadCases() {
  loadingCases.value = true;
  errorMessage.value = null;
  try {
    caseList.value = await apiService.getClinicalCases();
  } catch (error) {
    errorMessage.value = `Impossible de charger les stations. ${messageOf(error)}`;
  } finally {
    loadingCases.value = false;
  }
}

onMounted(loadCases);

async function openInstructions(caseId: number) {
  openingCaseId.value = caseId;
  errorMessage.value = null;
  startError.value = null;
  try {
    popupContent.value = await apiService.getCaseInstructions(caseId);
    isVisible.value = true;
  } catch (error) {
    errorMessage.value = `Impossible d'afficher les consignes. ${messageOf(error)}`;
  } finally {
    openingCaseId.value = null;
  }
}

/** Reprend la tentative en cours s'il y en a une, sinon en crée une. */
async function startStation(caseId: number) {
  starting.value = true;
  startError.value = null;
  try {
    const active = await apiService.getActiveAttempt(caseId);
    const attempt = active ?? await apiService.createAttempt(caseId);
    isVisible.value = false;
    await router.push({ name: 'chat', params: { attemptId: attempt.id } });
  } catch (error) {
    startError.value = `La station n'a pas pu démarrer. ${messageOf(error)}`;
  } finally {
    starting.value = false;
  }
}

function formatDuration(seconds: number): string {
  const minutes = Math.round(seconds / 60);
  return `${minutes} min`;
}
</script>

<template>
  <div class="dashboard">
    <h1>Stations</h1>
    <p v-if="authStore.user" class="welcome">Bienvenue, {{ authStore.displayName }} !</p>

    <Message v-if="errorMessage" severity="error" :closable="false" class="page-error">
      <span>{{ errorMessage }}</span>
      <Button v-if="!caseList.length" label="Réessayer" icon="pi pi-refresh" size="small" text @click="loadCases" />
    </Message>

    <InstructionPopup
      v-if="popupContent"
      v-model:visible="isVisible"
      :header="popupContent.title || 'Consignes'"
    >
      <p class="popup-meta">Durée : {{ formatDuration(popupContent.duration_seconds) }}</p>
      <div class="instructions">{{ popupContent.student_instructions }}</div>
      <Message v-if="startError" severity="error" :closable="false" class="start-error">{{ startError }}</Message>
      <div class="popup-actions">
        <Button label="Fermer" severity="secondary" text @click="isVisible = false" />
        <Button
          label="Commencer la station"
          icon="pi pi-play"
          :loading="starting"
          @click="startStation(popupContent.case_id)"
        />
      </div>
    </InstructionPopup>

    <p v-if="loadingCases" class="muted" role="status">Chargement des stations…</p>
    <p v-else-if="!errorMessage && !caseList.length" class="muted">Aucune station disponible pour le moment.</p>

    <ul v-if="caseList.length" class="case-container" aria-label="Stations disponibles">
      <li v-for="caseItem in caseList" :key="caseItem.id">
        <Card class="case-card">
          <template #title><h2 class="case-title">{{ caseItem.title }}</h2></template>
          <template #subtitle>
            <p>{{ STATION_TYPE_LABELS[caseItem.station_type] ?? caseItem.station_type }}</p>
            <p v-if="caseItem.disciplines.length">{{ caseItem.disciplines.join(', ') }}</p>
            <p>Durée : {{ formatDuration(caseItem.duration_seconds) }}</p>
          </template>
          <template #footer>
            <div class="card-footer">
              <Button
                label="Voir les consignes"
                :aria-label="`Voir les consignes : ${caseItem.title}`"
                text
                :loading="openingCaseId === caseItem.id"
                :disabled="openingCaseId !== null"
                @click="openInstructions(caseItem.id)"
              />
            </div>
          </template>
        </Card>
      </li>
    </ul>
  </div>
</template>

<style scoped>
.dashboard {
  padding: 1rem 0 3rem;
}

.welcome {
  color: #374151;
}

.muted {
  color: #4b5563;
}

.page-error :deep(.p-message-text) {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-wrap: wrap;
}

.case-container {
  list-style: none;
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(min(100%, 20rem), 1fr));
  gap: 1rem;
  margin: 2rem 0 0;
  padding: 1rem;
  background-color: #f1f5f9;
  border-radius: 12px;
}

.case-container > li {
  display: flex;
}

.case-card {
  width: 100%;
  min-height: 15rem;
  display: flex;
  flex-direction: column;
}

.case-title {
  margin: 0;
  font-size: 1.2rem;
  line-height: 1.3;
}

.case-card :deep(.p-card-subtitle) {
  color: #4b5563;
}

.case-card :deep(.p-card-subtitle p) {
  margin: 0.25rem 0;
}

.case-card :deep(.p-card-body) {
  display: flex;
  flex-direction: column;
  flex: 1;
}

.case-card :deep(.p-card-footer) {
  margin-top: auto;
}

.card-footer {
  display: flex;
  justify-content: flex-end;
}

.popup-meta {
  margin-top: 0;
  color: #4b5563;
}

.popup-actions {
  display: flex;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 0.5rem;
  padding-top: 2rem;
}

@media (max-width: 640px) {
  .case-container {
    padding: 0.5rem;
  }
}
</style>
