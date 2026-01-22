<template>
  <div class="cases-container">
    <!-- En-tête avec message de bienvenue -->
    <div class="welcome-header">
      <h1>Bonjour, {{ userName }} 👋</h1>
      <p class="subtitle">Sélectionnez un cas clinique pour commencer votre examen</p>
    </div>

    <!-- Filtres -->
    <div class="filters">
      <Dropdown 
        v-model="selectedStationType" 
        :options="stationTypes" 
        optionLabel="label"
        optionValue="value"
        placeholder="Type de station"
        showClear
        class="filter-dropdown"
        @change="loadCases"
      />
      
      <Dropdown 
        v-model="selectedDiscipline" 
        :options="disciplines" 
        placeholder="Discipline"
        showClear
        class="filter-dropdown"
        @change="loadCases"
      />
    </div>

    <!-- Loading -->
    <div v-if="loading" class="loading-container">
      <ProgressSpinner />
    </div>

    <!-- Message d'erreur -->
    <Message v-if="error" severity="error" @close="error = null">
      {{ error }}
    </Message>

    <!-- Grille de cas cliniques -->
    <div v-if="!loading && cases.length > 0" class="cases-grid">
      <Card 
        v-for="clinicalCase in cases" 
        :key="clinicalCase.id"
        class="case-card"
        @click="selectCase(clinicalCase)"
      >
        <template #header>
          <div class="case-header">
            <Tag :value="getStationTypeLabel(clinicalCase.station_type)" severity="info" />
            <span class="duration">
              <i class="pi pi-clock"></i>
              {{ formatDuration(clinicalCase.duration_seconds) }}
            </span>
          </div>
        </template>
        
        <template #title>
          {{ clinicalCase.title }}
        </template>
        
        <template #content>
          <!-- Disciplines -->
          <div v-if="clinicalCase.disciplines.length > 0" class="case-meta">
            <div class="meta-label">
              <i class="pi pi-book"></i>
              <span>Disciplines:</span>
            </div>
            <div class="meta-tags">
              <Tag 
                v-for="discipline in clinicalCase.disciplines" 
                :key="discipline"
                :value="discipline"
                severity="success"
                class="meta-tag"
              />
            </div>
          </div>

          <!-- Items EDN -->
          <div v-if="clinicalCase.edn_codes.length > 0" class="case-meta">
            <div class="meta-label">
              <i class="pi pi-list"></i>
              <span>Items EDN:</span>
            </div>
            <div class="meta-tags">
              <Tag 
                v-for="code in clinicalCase.edn_codes" 
                :key="code"
                :value="`Item ${code}`"
                severity="warning"
                class="meta-tag"
              />
            </div>
          </div>

          <!-- Grille d'évaluation -->
          <div class="case-meta">
            <Chip 
              :label="clinicalCase.has_evaluation_grid ? 'Grille d\'évaluation disponible' : 'Pas de grille'"
              :icon="clinicalCase.has_evaluation_grid ? 'pi pi-check-circle' : 'pi pi-info-circle'"
              :class="clinicalCase.has_evaluation_grid ? 'chip-success' : 'chip-secondary'"
            />
          </div>
        </template>
        
        <template #footer>
          <Button 
            label="Commencer l'examen" 
            icon="pi pi-play" 
            class="w-full"
            @click.stop="selectCase(clinicalCase)"
          />
        </template>
      </Card>
    </div>

    <!-- Message si aucun cas -->
    <div v-if="!loading && cases.length === 0" class="no-cases">
      <i class="pi pi-inbox" style="font-size: 3rem; color: var(--text-color-secondary);"></i>
      <p>Aucun cas clinique disponible pour le moment</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed } from 'vue';
import { apiService, type ClinicalCase } from '../services/api';
import { useAuthStore } from '../stores/auth';
import { useAttemptStore } from '../stores/attempt';
import Card from 'primevue/card';
import Button from 'primevue/button';
import Tag from 'primevue/tag';
import Chip from 'primevue/chip';
import Dropdown from 'primevue/dropdown';
import Message from 'primevue/message';
import ProgressSpinner from 'primevue/progressspinner';

const authStore = useAuthStore();
const attemptStore = useAttemptStore();

const cases = ref<ClinicalCase[]>([]);
const loading = ref(false);
const error = ref<string | null>(null);
const selectedStationType = ref<string | null>(null);
const selectedDiscipline = ref<string | null>(null);

const userName = computed(() => authStore.user?.username || 'Utilisateur');

const stationTypes = [
  { label: 'Interrogatoire patient', value: 'patient_interview' },
  { label: 'Analyse d\'examens', value: 'exam_analysis' },
  { label: 'Geste technique', value: 'procedure' },
  { label: 'Annonce de diagnostic', value: 'diagnosis_announcement' },
  { label: 'Station mixte', value: 'mixed' },
];

const disciplines = ref<string[]>([]);

const emit = defineEmits<{
  startAttempt: [caseId: number];
}>();

function getStationTypeLabel(type: string): string {
  const found = stationTypes.find(st => st.value === type);
  return found?.label || type;
}

function formatDuration(seconds: number): string {
  const minutes = Math.floor(seconds / 60);
  return `${minutes} min`;
}

async function loadCases() {
  loading.value = true;
  error.value = null;
  
  try {
    const filters: any = {};
    if (selectedStationType.value) filters.station_type = selectedStationType.value;
    if (selectedDiscipline.value) filters.discipline = selectedDiscipline.value;
    
    cases.value = await apiService.getClinicalCases(filters);
    
    // Extraire les disciplines uniques pour le filtre
    const allDisciplines = new Set<string>();
    cases.value.forEach(c => c.disciplines.forEach(d => allDisciplines.add(d)));
    disciplines.value = Array.from(allDisciplines).sort();
  } catch (e: any) {
    error.value = e.message || 'Erreur lors du chargement des cas cliniques';
  } finally {
    loading.value = false;
  }
}

async function selectCase(clinicalCase: ClinicalCase) {
  try {
    loading.value = true;
    // Charger le cas dans le store - Pinia unwrap automatiquement les refs
    attemptStore.currentCase = clinicalCase;
    // Réinitialiser l'état
    attemptStore.currentAttempt = null;
    attemptStore.timeRemaining = null;
    attemptStore.isExpired = false;
    attemptStore.isTimerStarted = false;
    
    emit('startAttempt', clinicalCase.id);
  } catch (e: any) {
    error.value = e.message || 'Erreur lors de la sélection du cas';
  } finally {
    loading.value = false;
  }
}

onMounted(() => {
  loadCases();
});
</script>

<style scoped>
.cases-container {
  max-width: 95%;
  width: 100%;
  margin: 0 auto;
  padding: 2rem;
}

@media (min-width: 1920px) {
  .cases-container {
    max-width: 1800px;
  }
}

.welcome-header {
  margin-bottom: 2rem;
  text-align: center;
}

.welcome-header h1 {
  font-size: 2.5rem;
  margin-bottom: 0.5rem;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

.subtitle {
  font-size: 1.1rem;
  color: var(--text-color-secondary);
}

.filters {
  display: flex;
  gap: 1rem;
  margin-bottom: 2rem;
  flex-wrap: wrap;
}

.filter-dropdown {
  flex: 1;
  min-width: 200px;
}

.loading-container {
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 400px;
}

.cases-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 1.5rem;
  margin-top: 2rem;
}

@media (min-width: 1440px) {
  .cases-grid {
    grid-template-columns: repeat(auto-fill, minmax(380px, 1fr));
    gap: 2rem;
  }
}

.case-card {
  cursor: pointer;
  transition: all 0.3s ease;
  height: 100%;
}

.case-card:hover {
  transform: translateY(-5px);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.15);
}

.case-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 1rem;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
}

.duration {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-weight: 500;
}

.case-meta {
  margin-bottom: 1rem;
}

.meta-label {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-bottom: 0.5rem;
  font-weight: 600;
  color: var(--text-color-secondary);
  font-size: 0.9rem;
}

.meta-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
}

.meta-tag {
  font-size: 0.85rem;
}

.chip-success {
  background-color: #d4edda;
  color: #155724;
}

.chip-secondary {
  background-color: #e2e3e5;
  color: #383d41;
}

.no-cases {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 400px;
  text-align: center;
  color: var(--text-color-secondary);
}

.no-cases p {
  margin-top: 1rem;
  font-size: 1.1rem;
}
</style>
