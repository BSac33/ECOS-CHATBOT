<script setup lang="ts">
// Relecture d'une correction par un enseignant : transcription, points et justifications modifiables,
// relance de la correction automatique
import { computed, onMounted, reactive, ref } from 'vue'
import { RouterLink } from 'vue-router'
import Button from 'primevue/button'
import InputNumber from 'primevue/inputnumber'
import Textarea from 'primevue/textarea'
import Message from 'primevue/message'
import Tag from 'primevue/tag'
import { useToast } from 'primevue/usetoast'
import ChatBubble from '../components/Message.vue'
import { apiService } from '../services/api'
import { errorMessage } from '../services/http'
import type { AttemptReview, ChatMessage, EvaluationItemResult, EvaluationResult } from '../types'

const props = defineProps<{ attemptId: string }>()
const toast = useToast()

const review = ref<AttemptReview | null>(null)
const loading = ref(true)
const loadError = ref<string | null>(null)

// ---------- Correction ----------
const evaluation = computed(() => review.value?.evaluation ?? null)
const reevaluating = ref(false)
const reevaluateError = ref<string | null>(null)

interface ItemDraft {
  /** null : champ vidé par l'enseignant */
  points: number | null
  justification: string
  saving: boolean
  error: string | null
}
const drafts = reactive<Record<string, ItemDraft>>({})

function resetDrafts(result: EvaluationResult | null) {
  for (const key of Object.keys(drafts)) delete drafts[key]
  for (const item of result?.items ?? []) {
    drafts[item.item_id] = { points: item.points_awarded, justification: item.justification, saving: false, error: null }
  }
}

function draftOf(item: EvaluationItemResult): ItemDraft {
  return drafts[item.item_id] ??= { points: item.points_awarded, justification: item.justification, saving: false, error: null }
}

function isDirty(item: EvaluationItemResult): boolean {
  const d = drafts[item.item_id]
  return !!d && (d.points !== item.points_awarded || d.justification.trim() !== item.justification.trim())
}

function setEvaluation(result: EvaluationResult) {
  if (review.value) review.value.evaluation = result
  resetDrafts(result)
}

// ---------- Transcription ----------
const transcript = computed<ChatMessage[]>(() => (review.value?.transcript ?? []).map((entry) => ({
  id: String(entry.id),
  role: entry.role,
  content: entry.content,
  created_at: entry.timestamp ?? '',
  modality: entry.modality ?? null,
  interrupted_by: entry.interrupted_by ?? null,
  spoken_content: entry.spoken_content ?? null,
})))

const studentName = computed(() => {
  const r = review.value
  if (!r) return ''
  return r.full_name ? `${r.full_name} (${r.username})` : r.username
})

function parseDate(iso: string): Date {
  return new Date(/[zZ]|[+-]\d\d:?\d\d$/.test(iso) ? iso : `${iso}Z`)
}

function fmtDate(iso: string | null | undefined): string {
  if (!iso) return ''
  return parseDate(iso).toLocaleString('fr-FR', { dateStyle: 'long', timeStyle: 'short' })
}

function fmt(value: number | null | undefined): string {
  return value == null ? '—' : (Math.round(value * 100) / 100).toLocaleString('fr-FR')
}

async function load() {
  loading.value = true
  loadError.value = null
  try {
    review.value = await apiService.getAttemptReview(props.attemptId)
    resetDrafts(review.value.evaluation)
  } catch (e) {
    loadError.value = `Impossible de charger la tentative. ${errorMessage(e)}`
  } finally {
    loading.value = false
  }
}

async function saveItem(item: EvaluationItemResult) {
  const draft = draftOf(item)
  draft.error = null
  const points = draft.points == null ? NaN : Number(draft.points)
  if (!Number.isFinite(points) || points < 0 || points > item.points_possible || Math.round(points * 2) !== points * 2) {
    draft.error = `Points entre 0 et ${fmt(item.points_possible)}, par pas de 0,5.`
    return
  }
  draft.saving = true
  try {
    const response = await apiService.updateEvaluationItem(props.attemptId, item.item_id, {
      points_awarded: points,
      justification: draft.justification.trim(),
    })
    setEvaluation(response.evaluation)
    toast.add({ severity: 'success', summary: 'Item enregistré', detail: 'La note a été recalculée.', life: 4000 })
  } catch (e) {
    draftOf(item).error = errorMessage(e)
  } finally {
    draftOf(item).saving = false
  }
}

function cancelItem(item: EvaluationItemResult) {
  drafts[item.item_id] = { points: item.points_awarded, justification: item.justification, saving: false, error: null }
}

/** Relance (ou lance) la correction automatique : peut prendre plusieurs minutes, 503 possible. */
async function reevaluate() {
  if (evaluation.value && !window.confirm(
    'Relancer la correction remplace la correction actuelle, y compris vos modifications. Continuer ?')) {
    return
  }
  reevaluating.value = true
  reevaluateError.value = null
  try {
    const response = await apiService.reevaluateAttempt(props.attemptId)
    setEvaluation(response.evaluation)
    toast.add({ severity: 'success', summary: 'Correction terminée', life: 4000 })
  } catch (e) {
    reevaluateError.value = errorMessage(e, 'La correction automatique n’a pas abouti. Réessayez.')
  } finally {
    reevaluating.value = false
  }
}

onMounted(load)
</script>

<template>
  <div class="review-page">
    <p v-if="review" class="back">
      <RouterLink :to="{ name: 'case-editor', params: { caseId: review.case_id } }">
        Retour à la station
      </RouterLink>
    </p>

    <h1>Relecture de la correction</h1>
    <p v-if="loading" role="status">Chargement…</p>
    <Message v-if="loadError" severity="error" :closable="false">
      {{ loadError }}
      <Button label="Réessayer" icon="pi pi-refresh" size="small" text @click="load" />
    </Message>

    <template v-if="review">
      <p class="meta">
        <strong>{{ review.case_title }}</strong> · {{ studentName }}
        <template v-if="review.completed_at"> · terminée le {{ fmtDate(review.completed_at) }}</template>
        <template v-else> · non terminée</template>
      </p>

      <div class="layout">
        <!-- Transcription -->
        <section class="panel transcript" aria-labelledby="transcript-title">
          <h2 id="transcript-title">Transcription</h2>
          <p v-if="!transcript.length" class="muted">Aucun échange enregistré.</p>
          <div class="messages">
            <ChatBubble v-for="m in transcript" :key="m.id" :message="m" />
          </div>
        </section>

        <!-- Correction -->
        <section class="panel correction" aria-labelledby="correction-title">
          <div class="correction-head">
            <h2 id="correction-title">Correction</h2>
            <Button
              :label="evaluation ? 'Relancer la correction' : 'Corriger'"
              :icon="evaluation ? 'pi pi-refresh' : 'pi pi-check-square'"
              :severity="evaluation ? 'secondary' : undefined"
              :outlined="!!evaluation"
              size="small"
              :loading="reevaluating"
              @click="reevaluate"
            />
          </div>
          <p class="sr-only" role="status">{{ reevaluating ? 'Correction en cours, cela peut prendre quelques minutes…' : '' }}</p>
          <Message v-if="reevaluateError" severity="error" :closable="false">{{ reevaluateError }}</Message>

          <p v-if="!evaluation" class="muted">Cette tentative n'a pas encore été corrigée.</p>

          <template v-else>
            <div class="summary">
              <p class="score">
                <template v-if="evaluation.score_20 != null">
                  <strong>{{ fmt(evaluation.score_20) }} / 20</strong>
                  · grille {{ fmt(evaluation.items_score ?? evaluation.total_score) }} / {{ fmt(evaluation.items_possible ?? evaluation.total_possible) }}
                </template>
                <template v-else>
                  <strong>{{ fmt(evaluation.total_score) }} / {{ fmt(evaluation.total_possible) }}</strong>
                  ({{ fmt(evaluation.percentage) }} %)
                </template>
              </p>
              <Tag v-if="evaluation.needs_review" value="Relecture conseillée" severity="warn" icon="pi pi-exclamation-triangle" />
              <p v-if="evaluation.reviewed_at" class="reviewed">
                <i class="pi pi-check-circle" aria-hidden="true"></i>
                Relue<template v-if="evaluation.reviewed_by"> par {{ evaluation.reviewed_by }}</template>
                le {{ fmtDate(evaluation.reviewed_at) }}
              </p>
            </div>

            <h3 class="section-title">Items de la grille</h3>
            <article v-for="(item, index) in evaluation.items" :key="item.item_id" class="item"
                     :class="{ validated: item.is_validated, dirty: isDirty(item) }">
              <header class="item-head">
                <h4>{{ index + 1 }}. {{ item.criterion }}</h4>
                <span class="item-status">{{ item.is_validated ? 'Validé' : 'Non validé' }}</span>
                <Tag v-if="item.overridden" value="modifié par l'enseignant" severity="info" icon="pi pi-user-edit" />
              </header>

              <blockquote v-if="item.citation" class="citation">« {{ item.citation }} »</blockquote>
              <p v-if="item.citation && item.citation_found === false" class="citation-warning">
                <i class="pi pi-exclamation-triangle" aria-hidden="true"></i>
                Citation introuvable telle quelle dans la transcription : à vérifier.
              </p>

              <form class="item-form" @submit.prevent="saveItem(item)">
                <div class="field points">
                  <label :for="`points-${item.item_id}`">Points (sur {{ fmt(item.points_possible) }})</label>
                  <InputNumber
                    v-model="draftOf(item).points"
                    :input-id="`points-${item.item_id}`"
                    :min="0"
                    :max="item.points_possible"
                    :step="0.5"
                    :min-fraction-digits="0"
                    :max-fraction-digits="1"
                    show-buttons
                    locale="fr-FR"
                  />
                </div>
                <div class="field justification">
                  <label :for="`justification-${item.item_id}`">Justification</label>
                  <Textarea :id="`justification-${item.item_id}`" v-model="draftOf(item).justification" auto-resize rows="2" fluid />
                </div>
                <Message v-if="draftOf(item).error" severity="error" :closable="false" class="item-error">
                  {{ draftOf(item).error }}
                </Message>
                <div class="item-actions">
                  <Button type="submit" label="Enregistrer" icon="pi pi-check" size="small"
                          :disabled="!isDirty(item)" :loading="draftOf(item).saving" />
                  <Button v-if="isDirty(item)" type="button" label="Annuler" size="small" text severity="secondary"
                          @click="cancelItem(item)" />
                </div>
              </form>
            </article>

            <template v-if="evaluation.scales?.length || evaluation.global_performance">
              <h3 class="section-title">Échelles d'attitude</h3>
              <dl class="scales">
                <template v-for="sc in evaluation.scales ?? []" :key="sc.scale_id">
                  <dt>{{ sc.label }}</dt>
                  <dd>
                    <strong>{{ sc.level != null ? `${sc.level}/4 · ${sc.level_name}` : (sc.observable ? 'non évaluée' : 'non évaluable') }}</strong>
                    <span v-if="sc.justification"> — {{ sc.justification }}</span>
                  </dd>
                </template>
                <template v-if="evaluation.global_performance">
                  <dt>{{ evaluation.global_performance.label }}</dt>
                  <dd>
                    <strong>{{ evaluation.global_performance.level != null
                      ? `${evaluation.global_performance.level}/4 · ${evaluation.global_performance.level_name}` : 'non évaluée' }}</strong>
                    <span v-if="evaluation.global_performance.justification"> — {{ evaluation.global_performance.justification }}</span>
                  </dd>
                </template>
              </dl>
            </template>

            <h3 class="section-title">Retour global</h3>
            <p class="feedback">{{ evaluation.general_feedback }}</p>
          </template>
        </section>
      </div>
    </template>
  </div>
</template>

<style scoped>
.review-page { padding: 1rem 0 3rem; }
.back { margin: 0.5rem 0 0; }
h1 { font-size: 1.6rem; margin: 0.5rem 0; }
.meta { color: #374151; margin: 0 0 1rem; }
.layout { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1.2fr); gap: 1.25rem; align-items: start; }
.panel { border: 1px solid #e2e8f0; border-radius: 12px; padding: 1rem; min-width: 0; }
.panel h2 { margin: 0 0 0.75rem; font-size: 1.2rem; }
.transcript { position: sticky; top: 0; max-height: calc(100vh - 2rem); overflow-y: auto; }
.messages :deep(.message-bubble) { max-width: 90%; }
.correction-head { display: flex; justify-content: space-between; align-items: center; gap: 0.5rem; flex-wrap: wrap; }
.correction-head h2 { margin: 0; }
.summary { display: flex; flex-direction: column; align-items: flex-start; gap: 0.4rem; margin: 0.75rem 0; }
.summary p { margin: 0; }
.score { font-size: 1.1rem; }
.reviewed { color: #065f46; font-weight: 600; }
.section-title { font-size: 1.05rem; margin: 1.25rem 0 0.5rem; }
.item { border: 1px solid #e2e8f0; border-left: 4px solid #b91c1c; border-radius: 10px; padding: 0.75rem; margin-bottom: 0.75rem;
  display: flex; flex-direction: column; gap: 0.5rem; }
.item.validated { border-left-color: #047857; }
.item.dirty { background: #fffbeb; }
.item-head { display: flex; flex-wrap: wrap; align-items: center; gap: 0.35rem 0.75rem; }
.item-head h4 { margin: 0; font-size: 1rem; flex: 1 1 100%; }
.item-status { font-weight: 600; font-size: 0.9rem; color: #991b1b; }
.item.validated .item-status { color: #065f46; }
.citation { margin: 0; padding: 0.4rem 0.6rem; border-left: 3px solid #64748b; font-style: italic; color: #374151; font-size: 0.92rem; }
.citation-warning { margin: 0; font-size: 0.85rem; color: #92400e; }
.item-form { display: flex; flex-direction: column; gap: 0.5rem; }
.field { display: flex; flex-direction: column; gap: 0.25rem; }
.field label { font-weight: 600; font-size: 0.88rem; color: #334155; }
.field.points :deep(.p-inputnumber) { max-width: 10rem; }
.item-actions { display: flex; gap: 0.25rem; flex-wrap: wrap; }
.scales { display: grid; grid-template-columns: minmax(10rem, max-content) 1fr; gap: 0.4rem 1rem; margin: 0; font-size: 0.92rem; }
.scales dt { font-weight: 600; color: #334155; }
.scales dd { margin: 0; color: #374151; }
.feedback { white-space: pre-wrap; color: #374151; margin: 0; }
.muted { color: #475569; }
@media (max-width: 1100px) {
  .layout { grid-template-columns: minmax(0, 1fr); }
  .transcript { position: static; max-height: 60vh; }
}
@media (max-width: 640px) {
  .scales { grid-template-columns: 1fr; }
}
</style>
