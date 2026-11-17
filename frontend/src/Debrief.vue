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
        <div v-if="evaluation.score_20 != null" class="score-value">
          <span class="points-obtained">{{ fmt(evaluation.score_20) }}</span>
          <span class="separator">/</span>
          <span class="points-possible">20</span>
        </div>
        <div v-else class="score-value">
          <span class="points-obtained">{{ evaluation.total_score }}</span>
          <span class="separator">/</span>
          <span class="points-possible">{{ evaluation.points_possible }}</span>
        </div>
        <div v-if="evaluation.score_20 != null" class="score-detail">
          Grille : {{ fmt(evaluation.total_score) }} / {{ fmt(evaluation.points_possible) }} items observés
          <template v-if="ratedScales.length">
            · Attitudes : {{ fmt(scalesMean) }} / 4 en moyenne
            ({{ Math.round((evaluation.attitude_weight ?? 0) * 100) }} % de la note)
          </template>
        </div>
        <div v-else class="score-percentage">
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

        <!-- Échelles d'attitude et performance globale (format des ECOS nationaux) -->
        <div v-if="evaluation.scales.length || evaluation.global_performance" class="scales">
          <h2>Communication et attitudes</h2>
          <div v-for="sc in evaluation.scales" :key="sc.scale_id" class="scale" :class="{ unrated: sc.level == null }">
            <div class="scale-head">
              <span class="scale-label">{{ sc.label }}</span>
              <span v-if="sc.level != null" class="scale-level" :class="`level-${sc.level}`">
                {{ sc.level }}/4 · {{ sc.level_name }}
              </span>
              <span v-else class="scale-level none">{{ sc.observable ? 'non évaluée' : 'non évaluable ici' }}</span>
            </div>
            <p v-if="sc.justification" class="scale-why">{{ sc.justification }}</p>
          </div>
          <div v-if="evaluation.global_performance" class="scale global">
            <div class="scale-head">
              <span class="scale-label">{{ evaluation.global_performance.label }}</span>
              <span v-if="evaluation.global_performance.level != null" class="scale-level"
                    :class="`level-${evaluation.global_performance.level}`">
                {{ evaluation.global_performance.level }}/4 · {{ evaluation.global_performance.level_name }}
              </span>
            </div>
            <p v-if="evaluation.global_performance.justification" class="scale-why">
              {{ evaluation.global_performance.justification }}
            </p>
            <p class="scale-note">Indicative : elle n'entre pas dans la note.</p>
          </div>
        </div>

        <!-- Commentaire global -->
        <div class="global-feedback">
          <h2>Retour global</h2>
          <p>{{ evaluation.overall_feedback }}</p>
        </div>

        <!-- Consultation orale : en ECOS, on ne coupe pas la parole au patient -->
        <div v-if="oralConsultation" class="listening" :class="{ clean: interruptions.length === 0 }">
          <h2>Écoute du patient</h2>
          <p v-if="interruptions.length === 0">Vous n'avez jamais coupé la parole au patient.</p>
          <template v-else>
            <p>
              Vous avez coupé la parole au patient
              <strong>{{ interruptions.length }} fois</strong>.
              En ECOS, laissez le patient finir ses phrases : couper la parole est une faute de communication,
              et vous risquez de manquer une information.
            </p>
            <ul>
              <li v-for="cut in interruptions" :key="cut.message_id">
                <div class="heard">
                  Le patient disait : « {{ cut.spoken_content.replace(/\s*…$/, '') }}… »
                  <span class="reason">— coupé {{ reasonLabel(cut.reason) }}</span>
                </div>
                <div v-if="missedPart(cut)" class="missed">
                  Vous n'avez pas entendu : « {{ missedPart(cut) }} »
                </div>
              </li>
            </ul>
          </template>
        </div>

        <!-- Contenu pédagogique de la station (après la correction) -->
        <div v-if="hasTeaching" class="teaching">
          <h2>Pour aller plus loin</h2>
          <p v-if="teaching!.source" class="teaching-source">{{ teaching!.source }}</p>
          <template v-if="teaching!.objectives.length">
            <h3>Objectifs pédagogiques</h3>
            <ol><li v-for="(o, i) in teaching!.objectives" :key="i">{{ o }}</li></ol>
          </template>
          <template v-if="teaching!.key_points.length">
            <h3>Éléments clés de l'évaluation</h3>
            <dl class="key-points">
              <template v-for="(k, i) in teaching!.key_points" :key="i">
                <dt>{{ k.label }}</dt><dd>{{ k.text }}</dd>
              </template>
            </dl>
          </template>
          <details v-if="teaching!.model_script">
            <summary>Proposition de script</summary>
            <div class="long-text"><p v-for="(para, i) in paragraphs(teaching!.model_script)" :key="i">{{ para }}</p></div>
          </details>
          <details v-if="teaching!.comments" open>
            <summary>Commentaires</summary>
            <div class="long-text"><p v-for="(para, i) in paragraphs(teaching!.comments)" :key="i">{{ para }}</p></div>
          </details>
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

interface ScaleRating {
  scale_id: string;
  label: string;
  observable: boolean;
  level: number | null;
  level_name: string | null;
  justification: string | null;
}

interface GlobalPerformance {
  label: string;
  level: number | null;
  level_name: string | null;
  justification: string | null;
}

interface EvaluationRaw {
  items: EvaluationItemRaw[];
  total_score: number;
  total_possible: number;
  percentage: number;
  general_feedback: string;
  scales?: ScaleRating[];
  global_performance?: GlobalPerformance | null;
  attitude_weight?: number | null;
  score_20?: number | null;
}

interface Teaching {
  title: string | null;
  source: string | null;
  objectives: string[];
  key_points: { label: string; text: string }[];
  model_script: string;
  comments: string;
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
  scales: ScaleRating[];
  global_performance: GlobalPerformance | null;
  attitude_weight: number | null;
  score_20: number | null;
}

interface CaseInfo {
  title: string;
  edn_codes?: string[];
}

// Réplique du patient coupée par l'étudiant (consultation orale)
interface Interruption {
  message_id: string;
  reason: 'voice' | 'push_to_talk' | 'button' | string;
  spoken_content: string;
  full_reply: string;
}

const REASONS: Record<string, string> = {
  voice: 'en parlant par-dessus',
  push_to_talk: 'en reprenant le micro',
  button: 'avec le bouton « Interrompre »',
};

function reasonLabel(reason: string): string {
  return REASONS[reason] ?? '';
}

/** Partie de la réplique que le patient n'a pas pu prononcer. */
function missedPart(cut: Interruption): string {
  const heard = cut.spoken_content.replace(/\s*…$/, '').trim();
  return cut.full_reply.startsWith(heard) ? cut.full_reply.slice(heard.length).trim() : '';
}

const route = useRoute();
const attemptId = ref<string | null>(null);
const isLoading = ref(true);
const evaluation = ref<EvaluationData | null>(null);
const caseInfo = ref<CaseInfo | null>(null);
const oralConsultation = ref(false);
const interruptions = ref<Interruption[]>([]);
const teaching = ref<Teaching | null>(null);

const hasTeaching = computed(() => !!teaching.value && (teaching.value.objectives.length > 0
  || teaching.value.key_points.length > 0 || !!teaching.value.model_script || !!teaching.value.comments));
const ratedScales = computed(() => (evaluation.value?.scales ?? []).filter(s => s.level != null));
const scalesMean = computed(() => ratedScales.value.length
  ? ratedScales.value.reduce((sum, s) => sum + (s.level ?? 0), 0) / ratedScales.value.length : 0);

function paragraphs(text: string): string[] {
  return text.split(/\n+/).map(p => p.trim()).filter(Boolean);
}

function fmt(value: number): string {
  return (Math.round(value * 100) / 100).toLocaleString('fr-FR');
}

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
        })),
        scales: evalData.scales ?? [],
        global_performance: evalData.global_performance ?? null,
        attitude_weight: evalData.attitude_weight ?? null,
        score_20: evalData.score_20 ?? null,
      };
    }
    
    // 2. Récupérer les infos du transcript pour obtenir le case_id
    const transcriptResponse = await apiService.getAttemptTranscript(attemptId.value);
    console.log('=== DONNÉES TRANSCRIPT ===');
    console.log(JSON.stringify(transcriptResponse, null, 2));
    
    const caseId = transcriptResponse.case_id;
    oralConsultation.value = (transcriptResponse.transcript ?? [])
      .some((m: { modality?: string }) => m.modality === 'voice');
    interruptions.value = transcriptResponse.interruptions ?? [];
    
    // Contenu pédagogique de la station (facultatif)
    try {
      teaching.value = await apiService.getAttemptTeaching(attemptId.value);
    } catch {
      teaching.value = null;
    }

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
.score-detail {
  margin-top: .5rem;
  font-size: .95rem;
  color: rgba(255, 255, 255, .9);
}

.scales, .teaching {
  background: white;
  border-radius: 12px;
  padding: 1.5rem;
  margin-bottom: 1.5rem;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
}

.scales h2, .teaching h2 {
  margin: 0 0 1rem;
  font-size: 1.3rem;
  color: #1e293b;
}

.scale {
  border-top: 1px solid #e2e8f0;
  padding: .75rem 0;
}

.scale-head {
  display: flex;
  justify-content: space-between;
  gap: 1rem;
  flex-wrap: wrap;
  font-weight: 600;
  color: #1e293b;
}

.scale-level {
  border-radius: 999px;
  padding: .1rem .7rem;
  font-size: .85rem;
  white-space: nowrap;
}

.scale-level.level-0 { background: #fee2e2; color: #991b1b; }
.scale-level.level-1 { background: #fef3c7; color: #92400e; }
.scale-level.level-2 { background: #e0f2fe; color: #075985; }
.scale-level.level-3 { background: #dcfce7; color: #166534; }
.scale-level.level-4 { background: #bbf7d0; color: #14532d; }
.scale-level.none { background: #f1f5f9; color: #64748b; font-weight: 400; }

.scale-why {
  margin: .35rem 0 0;
  color: #475569;
  font-size: .92rem;
}

.scale-note {
  margin: .25rem 0 0;
  color: #94a3b8;
  font-size: .85rem;
}

.teaching h3 {
  font-size: 1.05rem;
  margin: 1.25rem 0 .5rem;
  color: #334155;
}

.teaching-source {
  color: #64748b;
  font-size: .9rem;
  margin: -.5rem 0 0;
}

.key-points {
  display: grid;
  grid-template-columns: minmax(8rem, 14rem) 1fr;
  gap: .4rem 1rem;
  margin: 0;
}

.key-points dt { font-weight: 600; color: #334155; }
.key-points dd { margin: 0; color: #475569; }

.teaching details {
  margin-top: 1rem;
}

.teaching summary {
  cursor: pointer;
  font-weight: 600;
  color: #334155;
}

.long-text {
  color: #334155;
  line-height: 1.55;
  margin-top: .5rem;
}

.long-text p {
  margin: 0 0 .6rem;
}

@media (max-width: 640px) {
  .key-points { grid-template-columns: 1fr; }
  .key-points dd { margin-bottom: .5rem; }
}

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

.listening {
  margin-top: 2rem;
  padding: 1.5rem;
  background: #fff7ed;
  border-left: 4px solid #f59e0b;
  border-radius: 12px;
}

.listening.clean {
  background: #f0fdf4;
  border-left-color: #22c55e;
}

.listening h2 {
  margin: 0 0 0.75rem;
  font-size: 1.25rem;
  color: #1f2937;
}

.listening ul {
  margin: 0.75rem 0 0;
  padding-left: 1.25rem;
}

.listening li {
  margin-bottom: 0.75rem;
}

.listening .reason {
  color: #92400e;
  font-size: 0.9rem;
}

.listening .missed {
  margin-top: 0.25rem;
  color: #6b7280;
  font-style: italic;
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
