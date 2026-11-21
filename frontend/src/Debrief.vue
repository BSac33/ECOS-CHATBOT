<template>
  <div class="debrief-container">
    <LoadingEvaluation v-if="isLoading" />

    <div v-else-if="evaluation" class="debrief-content">
      <header class="case-header">
        <h1>{{ caseTitle || 'Débriefing' }}</h1>
        <p class="ai-notice">
          <i class="pi pi-sparkles" aria-hidden="true"></i>
          Correction proposée par une intelligence artificielle<template v-if="!evaluation.reviewed_at">, sans relecture humaine à ce stade</template>.
        </p>
        <p v-if="evaluation.reviewed_at" class="reviewed">
          <i class="pi pi-check-circle" aria-hidden="true"></i>
          Correction relue par un enseignant le {{ fmtDate(evaluation.reviewed_at) }}.
        </p>
      </header>

      <!-- Note globale -->
      <section class="global-score" aria-label="Note">
        <p v-if="evaluation.score_20 != null" class="score-value">
          <span class="points-obtained">{{ fmt(evaluation.score_20) }}</span>
          <span class="separator" aria-hidden="true">/</span>
          <span class="sr-only"> sur </span>
          <span class="points-possible">20</span>
        </p>
        <p v-else class="score-value">
          <span class="points-obtained">{{ fmt(evaluation.total_score) }}</span>
          <span class="separator" aria-hidden="true">/</span>
          <span class="sr-only"> sur </span>
          <span class="points-possible">{{ fmt(evaluation.total_possible) }}</span>
        </p>
        <p v-if="evaluation.score_20 != null" class="score-detail">
          Grille : {{ fmt(itemsScore) }} / {{ fmt(itemsPossible) }} points
          <template v-if="ratedScales.length">
            · Attitudes : {{ fmt(scalesMean) }} / 4 en moyenne
            ({{ Math.round((evaluation.attitude_weight ?? 0) * 100) }} % de la note)
          </template>
        </p>
        <p v-else class="score-percentage">{{ scorePercentage }} %</p>
      </section>

      <!-- Items d'évaluation -->
      <section class="evaluation-items" aria-labelledby="grid-title">
        <h2 id="grid-title">Grille d'évaluation</h2>
        <EvaluationItem v-for="item in evaluation.items" :key="item.item_id" :item="item" />
      </section>

      <!-- Échelles d'attitude et performance globale (format des ECOS nationaux) -->
      <section v-if="scales.length || evaluation.global_performance" class="scales">
        <h2>Communication et attitudes</h2>
        <div v-for="sc in scales" :key="sc.scale_id" class="scale" :class="{ unrated: sc.level == null }">
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
      </section>

      <!-- Commentaire global -->
      <section class="global-feedback">
        <h2>Retour global</h2>
        <p>{{ evaluation.general_feedback }}</p>
      </section>

      <!-- Consultation orale : en ECOS, on ne coupe pas la parole au patient -->
      <section v-if="oralConsultation" class="listening" :class="{ clean: interruptions.length === 0 }">
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
      </section>

      <!-- Contenu pédagogique de la station (après la correction) -->
      <section v-if="teaching && hasTeaching" class="teaching">
        <h2>Pour aller plus loin</h2>
        <p v-if="teaching.source" class="teaching-source">{{ teaching.source }}</p>
        <template v-if="teaching.objectives.length">
          <h3>Objectifs pédagogiques</h3>
          <ol><li v-for="(o, i) in teaching.objectives" :key="i">{{ o }}</li></ol>
        </template>
        <template v-if="teaching.key_points.length">
          <h3>Éléments clés de l'évaluation</h3>
          <dl class="key-points">
            <template v-for="(k, i) in teaching.key_points" :key="i">
              <dt>{{ k.label }}</dt><dd>{{ k.text }}</dd>
            </template>
          </dl>
        </template>
        <details v-if="teaching.model_script">
          <summary>Proposition de script</summary>
          <div class="long-text"><p v-for="(para, i) in paragraphs(teaching.model_script)" :key="i">{{ para }}</p></div>
        </details>
        <details v-if="teaching.comments" open>
          <summary>Commentaires</summary>
          <div class="long-text"><p v-for="(para, i) in paragraphs(teaching.comments)" :key="i">{{ para }}</p></div>
        </details>
      </section>

      <!-- Pour approfondir -->
      <section class="resources">
        <h2>Pour approfondir</h2>
        <p v-if="ednCodes.length">Items EDN : {{ ednCodes.join(', ') }}</p>
        <p v-else>Aucun item EDN associé à cette station.</p>
      </section>

      <p class="back">
        <RouterLink :to="{ name: 'dashboard' }">Retour aux stations</RouterLink>
      </p>
    </div>

    <div v-else class="error-content">
      <h1>Correction indisponible</h1>
      <p role="alert">{{ loadError || 'Les données de correction n’ont pas pu être chargées.' }}</p>
      <div class="error-actions">
        <Button label="Réessayer" icon="pi pi-refresh" @click="runEvaluation" />
        <RouterLink :to="{ name: 'dashboard' }">Retour aux stations</RouterLink>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref, computed } from 'vue';
import { RouterLink } from 'vue-router';
import Button from 'primevue/button';
import LoadingEvaluation from './components/LoadingEvaluation.vue';
import EvaluationItem from './components/EvaluationItem.vue';
import { apiService } from './services/api';
import { errorMessage } from './services/http';
import type { EvaluationResult, Interruption, Teaching } from './types';

const props = defineProps<{ attemptId: string }>();

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

const isLoading = ref(true);
const loadError = ref<string | null>(null);
const evaluation = ref<EvaluationResult | null>(null);
const caseTitle = ref('');
const ednCodes = ref<number[]>([]);
const oralConsultation = ref(false);
const interruptions = ref<Interruption[]>([]);
const teaching = ref<Teaching | null>(null);

const scales = computed(() => evaluation.value?.scales ?? []);
const hasTeaching = computed(() => !!teaching.value && (teaching.value.objectives.length > 0
  || teaching.value.key_points.length > 0 || !!teaching.value.model_script || !!teaching.value.comments));
const ratedScales = computed(() => scales.value.filter(s => s.level != null));
const scalesMean = computed(() => ratedScales.value.length
  ? ratedScales.value.reduce((sum, s) => sum + (s.level ?? 0), 0) / ratedScales.value.length : 0);
const itemsScore = computed(() => evaluation.value?.items_score ?? evaluation.value?.total_score ?? 0);
const itemsPossible = computed(() => evaluation.value?.items_possible ?? evaluation.value?.total_possible ?? 0);
const scorePercentage = computed(() => {
  const e = evaluation.value;
  if (!e || !e.total_possible) return 0;
  return Math.round((e.total_score / e.total_possible) * 100);
});

function paragraphs(text: string): string[] {
  return text.split(/\n+/).map(p => p.trim()).filter(Boolean);
}

function fmt(value: number): string {
  return (Math.round(value * 100) / 100).toLocaleString('fr-FR');
}

function fmtDate(iso: string): string {
  const date = new Date(/[zZ]|[+-]\d\d:?\d\d$/.test(iso) ? iso : `${iso}Z`);
  return date.toLocaleDateString('fr-FR', { day: 'numeric', month: 'long', year: 'numeric' });
}

/** Informations annexes (titre, transcription, contenu pédagogique) : facultatives. */
async function loadContext() {
  const [info, transcript, teachingContent] = await Promise.allSettled([
    apiService.getAttemptCaseInfo(props.attemptId),
    apiService.getAttemptTranscript(props.attemptId),
    apiService.getAttemptTeaching(props.attemptId),
  ]);
  if (info.status === 'fulfilled') caseTitle.value = info.value.title;
  if (transcript.status === 'fulfilled') {
    oralConsultation.value = transcript.value.transcript.some(m => m.modality === 'voice');
    interruptions.value = transcript.value.interruptions ?? [];
    try {
      const caseData = await apiService.getClinicalCase(transcript.value.case_id);
      ednCodes.value = caseData.edn_codes ?? [];
      caseTitle.value ||= caseData.title;
    } catch {
      // station non publiée (test enseignant) : pas d'items EDN affichés
    }
  }
  teaching.value = teachingContent.status === 'fulfilled' ? teachingContent.value : null;
}

/** Correction (longue) : en cas d'échec (503...), message du serveur et bouton « Réessayer ». */
async function runEvaluation() {
  isLoading.value = true;
  loadError.value = null;
  try {
    const response = await apiService.evaluateAttempt(props.attemptId);
    evaluation.value = response.evaluation;
  } catch (error) {
    evaluation.value = null;
    loadError.value = errorMessage(error, 'La correction automatique n’a pas abouti. Réessayez.');
  } finally {
    isLoading.value = false;
  }
}

onMounted(async () => {
  await Promise.all([runEvaluation(), loadContext()]);
});
</script>

<style scoped>
.debrief-container {
  padding: 2rem 0 3rem;
}

.debrief-content {
  max-width: 1200px;
  margin: 0 auto;
}

.error-content {
  max-width: 48rem;
  margin: 2rem auto;
  padding: 2rem;
  background: white;
  border-radius: 12px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
  text-align: center;
}

.error-content h1 {
  font-size: 1.5rem;
  margin-top: 0;
}

.error-content p {
  color: #991b1b;
}

.error-actions {
  display: flex;
  justify-content: center;
  align-items: center;
  flex-wrap: wrap;
  gap: 1rem;
}

/* En-tête */
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

.case-header .ai-notice {
  margin-top: 0.5rem;
}

.reviewed {
  margin: 0.5rem 0 0;
  color: #065f46;
  font-weight: 600;
}

/* Note globale (texte blanc sur fond foncé : contraste ≥ 4,5:1) */
.global-score {
  background: linear-gradient(135deg, #4338ca 0%, #6d28d9 100%);
  padding: 2rem;
  border-radius: 16px;
  margin-bottom: 2rem;
  text-align: center;
  color: white;
  box-shadow: 0 8px 24px rgba(67, 56, 202, 0.25);
}

.global-score p {
  margin: 0;
}

.score-value {
  font-size: 4rem;
  font-weight: 800;
  line-height: 1;
  margin-bottom: 0.5rem !important;
}

.points-obtained {
  color: #ffffff;
}

.separator {
  margin: 0 0.5rem;
}

.points-possible {
  font-size: 3rem;
}

.score-percentage {
  font-size: 1.5rem;
  font-weight: 600;
}

.score-detail {
  margin-top: .5rem;
  font-size: .95rem;
}

/* Items d'évaluation */
.evaluation-items {
  display: flex;
  flex-direction: column;
  gap: 1rem;
  margin-bottom: 2rem;
}

.evaluation-items h2,
.scales h2,
.teaching h2,
.global-feedback h2,
.resources h2,
.listening h2 {
  margin: 0 0 1rem;
  font-size: 1.3rem;
  color: #1e293b;
}

.evaluation-items h2 {
  margin-bottom: 0;
}

.scales, .teaching {
  background: white;
  border-radius: 12px;
  padding: 1.5rem;
  margin-bottom: 1.5rem;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
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
.scale-level.none { background: #f1f5f9; color: #475569; font-weight: 400; }

.scale-why {
  margin: .35rem 0 0;
  color: #475569;
  font-size: .92rem;
}

.scale-note {
  margin: .25rem 0 0;
  color: #64748b;
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
  .score-value { font-size: 3rem; }
  .points-possible { font-size: 2.25rem; }
  .case-header h1 { font-size: 1.5rem; }
  .debrief-container { padding-top: 1rem; }
}

.global-feedback {
  background: white;
  padding: 2rem;
  border-radius: 12px;
  margin-bottom: 2rem;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
  border-left: 4px solid #4338ca;
}

.global-feedback p {
  font-size: 1rem;
  line-height: 1.6;
  color: #475569;
  margin: 0;
  white-space: pre-wrap;
}

.resources {
  background: white;
  padding: 2rem;
  border-radius: 12px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
  border-left: 4px solid #047857;
  margin-top: 2rem;
}

.resources p {
  font-size: 1rem;
  line-height: 1.6;
  color: #475569;
  margin: 0;
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
  color: #4b5563;
  font-style: italic;
}

.back {
  margin-top: 2rem;
  text-align: center;
}
</style>
