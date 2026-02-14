<template>
  <div class="debrief-container">
    <LoadingEvaluation v-if="isLoading" />
    
    <div v-else-if="evaluation && caseInfo" class="debrief-content">
      <!-- Header avec titre du cas -->
      <header class="case-header">
        <h1>{{ caseInfo.title }}</h1>
      </header>

      <!-- Note globale -->
      <div class="global-score">
        <div class="score-value">
          <span class="points-obtained">{{ evaluation.total_score }}</span>
          <span class="separator">/</span>
          <span class="points-possible">{{ evaluation.points_possible }}</span>
        </div>
        <div class="score-percentage">
          {{ scorePercentage }}%
        </div>
      </div>

      <!-- Container scrollable pour tout le contenu -->
      <div class="scrollable-content">
        <!-- Items d'évaluation -->
        <div class="evaluation-items">
          <EvaluationItem
            v-for="item in evaluation.items"
            :key="item.edn_code || item.item_name"
            :item="item"
          />
        </div>

        <!-- Commentaire global -->
        <div class="global-feedback">
          <h2>Retour global</h2>
          <p>{{ evaluation.overall_feedback }}</p>
        </div>

        <!-- Pour approfondir -->
        <div class="resources">
          <h2>Pour approfondir</h2>
          <div class="edn-codes">
            <p v-if="caseInfo.edn_codes && caseInfo.edn_codes.length > 0">
              Items EDN : {{ caseInfo.edn_codes.join(', ') }}
            </p>
            <p v-else>Aucun item EDN associé à ce cas.</p>
          </div>
        </div>
      </div>
    </div>

    <div v-else class="error-content">
      <p>Erreur lors du chargement des données d'évaluation.</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref, computed } from 'vue';
import { useRoute } from 'vue-router';
import { apiService } from './services/api';
import LoadingEvaluation from './components/LoadingEvaluation.vue';
import EvaluationItem from './components/EvaluationItem.vue';

// Structure réelle retournée par le LLM
interface EvaluationItemRaw {
  item_id: string;
  criterion: string;
  points_awarded: number;
  points_possible: number;
  is_validated: boolean;
  justification: string;
}

interface EvaluationRaw {
  items: EvaluationItemRaw[];
  total_score: number;
  total_possible: number;
  percentage: number;
  general_feedback: string;
}

interface EvaluationResponse {
  evaluation: EvaluationRaw;
}

// Structure pour le composant EvaluationItem
interface EvaluationItemData {
  edn_code?: string;
  item_name: string;
  points_obtained: number;
  points_possible: number;
  justification: string;
}

interface EvaluationData {
  total_score: number;
  points_possible: number;
  overall_feedback: string;
  items: EvaluationItemData[];
}

interface CaseInfo {
  title: string;
  edn_codes?: string[];
}

const route = useRoute();
const attemptId = ref<string | null>(null);
const isLoading = ref(true);
const evaluation = ref<EvaluationData | null>(null);
const caseInfo = ref<CaseInfo | null>(null);

const scorePercentage = computed(() => {
  if (!evaluation.value) return 0;
  return Math.round((evaluation.value.total_score / evaluation.value.points_possible) * 100);
});

onMounted(async () => {
  // Récupérer l'ID de l'attempt depuis les paramètres de route
  attemptId.value = route.params.attemptId as string;
  
  if (!attemptId.value) {
    console.error('Aucun attemptId fourni dans les paramètres de route');
    isLoading.value = false;
    return;
  }
  
  try {
    console.log('=== DÉBUT RÉCUPÉRATION DONNÉES DÉBRIEFING ===');
    console.log('Attempt ID:', attemptId.value);
    
    // 1. Récupérer l'évaluation de la tentative (c'est l'opération longue)
    const evaluationResponse = await apiService.getAttemptEvaluation(attemptId.value) as EvaluationResponse;
    console.log('=== DONNÉES ÉVALUATION ===');
    console.log(JSON.stringify(evaluationResponse, null, 2));
    
    // Mapper les données vers la structure attendue par les composants
    if (evaluationResponse && evaluationResponse.evaluation) {
      const evalData = evaluationResponse.evaluation;
      evaluation.value = {
        total_score: evalData.total_score,
        points_possible: evalData.total_possible,
        overall_feedback: evalData.general_feedback,
        items: evalData.items.map(item => ({
          edn_code: item.item_id,
          item_name: item.criterion,
          points_obtained: item.points_awarded,
          points_possible: item.points_possible,
          justification: item.justification
        }))
      };
    }
    
    // 2. Récupérer les infos du transcript pour obtenir le case_id
    const transcriptResponse = await apiService.getAttemptTranscript(attemptId.value);
    console.log('=== DONNÉES TRANSCRIPT ===');
    console.log(JSON.stringify(transcriptResponse, null, 2));
    
    const caseId = transcriptResponse.case_id;
    
    // 3. Récupérer les infos du case
    const caseData = await apiService.getClinicalCase(caseId);
    console.log('=== DONNÉES CASE ===');
    console.log(JSON.stringify(caseData, null, 2));
    caseInfo.value = caseData;
    
    console.log('=== FIN RÉCUPÉRATION DONNÉES DÉBRIEFING ===');
  } catch (error) {
    console.error('Erreur lors de la récupération des données:', error);
  } finally {
    isLoading.value = false;
  }
});
</script>

<style scoped>
.debrief-container {
  padding: 2rem;
  background: linear-gradient(to bottom, #f8fafc, #ffffff);
  min-height: 100vh;
}

.debrief-content {
  max-width: 1200px;
  margin: 0 auto;
}

.error-content {
  max-width: 1200px;
  margin: 0 auto;
  padding: 2rem;
  background: white;
  border-radius: 12px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
  text-align: center;
  color: #ef4444;
}

/* Header du cas */
.case-header {
  margin-bottom: 2rem;
  text-align: center;
}

.case-header h1 {
  font-size: 2rem;
  font-weight: 700;
  color: #1e293b;
  margin: 0;
}

/* Note globale */
.global-score {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  padding: 2rem;
  border-radius: 16px;
  margin-bottom: 2rem;
  text-align: center;
  color: white;
  box-shadow: 0 8px 24px rgba(102, 126, 234, 0.3);
}

.score-value {
  font-size: 4rem;
  font-weight: 800;
  line-height: 1;
  margin-bottom: 0.5rem;
}

.points-obtained {
  color: #ffffff;
}

.separator {
  color: rgba(255, 255, 255, 0.7);
  margin: 0 0.5rem;
}

.points-possible {
  color: rgba(255, 255, 255, 0.9);
  font-size: 3rem;
}

.score-percentage {
  font-size: 1.5rem;
  font-weight: 600;
  color: rgba(255, 255, 255, 0.95);
}

/* Container scrollable */
.scrollable-content {
  max-height: calc(100vh - 350px);
  overflow-y: auto;
  padding-right: 0.5rem;
}

/* Scrollbar styling pour Webkit browsers */
.scrollable-content::-webkit-scrollbar {
  width: 8px;
}

.scrollable-content::-webkit-scrollbar-track {
  background: #f1f5f9;
  border-radius: 4px;
}

.scrollable-content::-webkit-scrollbar-thumb {
  background: #cbd5e1;
  border-radius: 4px;
}

.scrollable-content::-webkit-scrollbar-thumb:hover {
  background: #94a3b8;
}

/* Items d'évaluation */
.evaluation-items {
  display: flex;
  flex-direction: column;
  gap: 1rem;
  margin-bottom: 2rem;
}

/* Commentaire global */
.global-feedback {
  background: white;
  padding: 2rem;
  border-radius: 12px;
  margin-bottom: 2rem;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
  border-left: 4px solid #667eea;
}

.global-feedback h2 {
  font-size: 1.5rem;
  font-weight: 700;
  color: #1e293b;
  margin: 0 0 1rem 0;
}

.global-feedback p {
  font-size: 1rem;
  line-height: 1.6;
  color: #475569;
  margin: 0;
  white-space: pre-wrap;
}

/* Section pour approfondir */
.resources {
  background: white;
  padding: 2rem;
  border-radius: 12px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
  border-left: 4px solid #10b981;
  margin-bottom: 0;
}

.resources h2 {
  font-size: 1.5rem;
  font-weight: 700;
  color: #1e293b;
  margin: 0 0 1rem 0;
}

.edn-codes p {
  font-size: 1rem;
  line-height: 1.6;
  color: #475569;
  margin: 0;
}
</style>
