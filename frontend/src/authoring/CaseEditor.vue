<script setup lang="ts">
// Éditeur d'une station : fiche structurée, vérifications, assistant, test et publication
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import Button from 'primevue/button'
import InputText from 'primevue/inputtext'
import InputNumber from 'primevue/inputnumber'
import Textarea from 'primevue/textarea'
import Select from 'primevue/select'
import MultiSelect from 'primevue/multiselect'
import Message from 'primevue/message'
import Tag from 'primevue/tag'
import Tabs from 'primevue/tabs'
import TabList from 'primevue/tablist'
import Tab from 'primevue/tab'
import TabPanels from 'primevue/tabpanels'
import TabPanel from 'primevue/tabpanel'
import FactsEditor from './FactsEditor.vue'
import GridEditor from './GridEditor.vue'
import StringList from './StringList.vue'
import AssistantPanel from './AssistantPanel.vue'
import CorpusSearch from './CorpusSearch.vue'
import {
  ApiError, authoringApi, type CaseDetail, type CaseSheet, type Issue, type ReferenceItem, type ReferenceSituation,
} from './api'

const props = defineProps<{ caseId: string }>()
const router = useRouter()
const id = computed(() => Number(props.caseId))

const detail = ref<CaseDetail | null>(null)
const sheet = ref<CaseSheet | null>(null)
const loadError = ref('')
const tab = ref('station')
const side = ref('checks')

// ---------- Enregistrement automatique ----------
const saveState = ref<'saved' | 'dirty' | 'saving' | 'error'>('saved')
const savedAt = ref<Date | null>(null)
let timer: ReturnType<typeof setTimeout> | null = null
let applyingServer = false

async function load() {
  try {
    const d = await authoringApi.getCase(id.value)
    applyDetail(d)
  } catch (e: any) {
    loadError.value = e.message
  }
}

function applyDetail(d: CaseDetail) {
  detail.value = d
  if (!sheet.value && d.sheet) {
    applyingServer = true
    sheet.value = d.sheet
    nextTick(() => { applyingServer = false })
  }
}

async function save(): Promise<boolean> {
  if (!sheet.value) return false
  if (timer) { clearTimeout(timer); timer = null }
  saveState.value = 'saving'
  try {
    const d = await authoringApi.saveSheet(id.value, sheet.value)
    detail.value = d                       // vérifications et aperçu à jour (la fiche locale reste)
    savedAt.value = new Date()
    saveState.value = timer ? 'dirty' : 'saved'
    return true
  } catch (e) {
    saveState.value = 'error'
    return false
  }
}

watch(sheet, () => {
  if (applyingServer || !detail.value?.can_edit) return
  saveState.value = 'dirty'
  if (timer) clearTimeout(timer)
  timer = setTimeout(() => { timer = null; save() }, 1200)
}, { deep: true })

function beforeUnload(e: BeforeUnloadEvent) {
  if (saveState.value === 'dirty' || saveState.value === 'saving') e.preventDefault()
}

// ---------- Référentiels ----------
const items = ref<ReferenceItem[]>([])
const situations = ref<ReferenceSituation[]>([])
const itemOptions = computed(() => items.value.map((i) => ({ value: i.number, label: `${i.number} – ${i.title}` })))
const situationOptions = computed(() => situations.value.map((s) => ({
  value: s.number, label: `${s.number} – ${s.title}`, group: s.linked ? 'Liées aux items choisis' : 'Autres situations',
})))
const situationGroups = computed(() => ['Liées aux items choisis', 'Autres situations']
  .map((label) => ({ label, items: situationOptions.value.filter((s) => s.group === label) }))
  .filter((g) => g.items.length))

async function loadSituations() {
  try {
    situations.value = await authoringApi.situations(sheet.value?.station.edn_items || [])
  } catch { /* référentiel absent : liste vide */ }
}
watch(() => sheet.value?.station.edn_items.join(','), loadSituations)

const VOICES = [
  { value: null, label: 'Voix par défaut du serveur' },
  { value: 'unmute-prod-website/fabieng-enhanced-v2.wav', label: 'Homme (fabieng)' },
  { value: 'unmute-prod-website/developpeuse-3.wav', label: 'Femme (developpeuse)' },
]
const voiceOptions = computed(() => {
  const current = sheet.value?.station.voice_id
  return current && !VOICES.some((v) => v.value === current) ? [...VOICES, { value: current, label: current }] : VOICES
})
const SEX = [{ value: 'femme', label: 'Femme' }, { value: 'homme', label: 'Homme' }, { value: 'autre', label: 'Autre' }]
const REGISTERS = [
  { value: 'courant', label: 'Courant' }, { value: 'simple', label: 'Simple' },
  { value: 'familier', label: 'Familier' }, { value: 'soutenu', label: 'Soutenu' },
]

// ---------- Vérifications ----------
const issues = computed<Issue[]>(() => detail.value?.issues || [])
const counts = computed(() => ({
  erreur: issues.value.filter((i) => i.level === 'erreur').length,
  attention: issues.value.filter((i) => i.level === 'attention').length,
  conseil: issues.value.filter((i) => i.level === 'conseil').length,
}))
const LEVEL = {
  erreur: { label: 'À corriger avant publication', severity: 'danger', icon: 'pi pi-times-circle' },
  attention: { label: 'À vérifier', severity: 'warn', icon: 'pi pi-exclamation-triangle' },
  conseil: { label: 'Conseil', severity: 'secondary', icon: 'pi pi-info-circle' },
} as const

function tabFor(field: string) {
  if (field.startsWith('station')) return 'station'
  if (field.startsWith('patient')) return 'patient'
  if (field.startsWith('correction')) return 'correction'
  return 'faits'
}
async function jump(issue: Issue) {
  tab.value = tabFor(issue.field)
  await nextTick()
  const el = document.querySelector<HTMLElement>(`[data-field="${issue.field}"]`)
    || document.querySelector<HTMLElement>(`[data-field="${issue.field.split('[')[0]}"]`)
  if (el) {
    el.scrollIntoView({ behavior: 'smooth', block: 'center' })
    el.classList.add('flash')
    setTimeout(() => el.classList.remove('flash'), 1600)
  }
}
const pendingReview = computed(() => {
  const s = sheet.value
  if (!s) return 0
  return s.facts.filter((f) => f.generated).length + s.correction.grid.filter((g) => g.generated).length
    + s.exam_findings.filter((e) => e.generated).length + s.patient.reactions.filter((r) => r.generated).length
})

// ---------- Tester / publier ----------
const busy = ref<'test' | 'publish' | null>(null)
const banner = ref<{ severity: 'success' | 'error' | 'warn'; text: string } | null>(null)

async function testPatient() {
  busy.value = 'test'
  banner.value = null
  try {
    if (canEdit.value && !(await save())) throw new Error('Enregistrement impossible.')
    const { attempt_id } = await authoringApi.test(id.value)
    window.open(router.resolve({ name: 'chat', params: { attemptId: attempt_id } }).href, '_blank')
    detail.value = await authoringApi.getCase(id.value)
  } catch (e: any) {
    banner.value = { severity: 'error', text: e.message }
  } finally {
    busy.value = null
  }
}

async function publish() {
  busy.value = 'publish'
  banner.value = null
  try {
    if (!(await save())) throw new Error('Enregistrement impossible.')
    const { version } = await authoringApi.publish(id.value)
    banner.value = { severity: 'success', text: `Version ${version.version} publiée : les nouvelles tentatives des étudiants utiliseront cette version.` }
    detail.value = await authoringApi.getCase(id.value)
  } catch (e: any) {
    if (e instanceof ApiError && e.status === 422) {
      side.value = 'checks'
      banner.value = { severity: 'error', text: 'Corrigez les erreurs signalées avant de publier.' }
    } else {
      banner.value = { severity: 'error', text: e.message }
    }
  } finally {
    busy.value = null
  }
}

const published = computed(() => detail.value?.versions.filter((v) => v.status === 'published') || [])
const tests = computed(() => detail.value?.versions.filter((v) => v.status === 'test') || [])
const title = computed(() => sheet.value?.station.title || 'Station sans titre')

// ---------- Relecture (facultative, ne bloque pas la publication) ----------
const reviewNote = ref('')
const reviewBusy = ref(false)
const canEdit = computed(() => !!detail.value?.can_edit)
const review = computed(() => detail.value?.review)
const fmtDate = (iso: string | null) => (iso ? new Date(iso).toLocaleDateString('fr-FR', { day: 'numeric', month: 'long' }) : '')

async function reviewAction(action: 'request' | 'clear' | 'mark') {
  reviewBusy.value = true
  banner.value = null
  try {
    if (action === 'request') detail.value = await authoringApi.requestReview(id.value)
    else if (action === 'clear') detail.value = await authoringApi.clearReview(id.value)
    else {
      detail.value = await authoringApi.markReviewed(id.value, reviewNote.value)
      reviewNote.value = ''
      banner.value = { severity: 'success', text: 'Merci : la station est marquée comme relue.' }
    }
  } catch (e: any) {
    banner.value = { severity: 'error', text: e.message }
  } finally {
    reviewBusy.value = false
  }
}

function onApplied(where: string) {
  tab.value = where === 'facts' ? 'faits' : where
}

onMounted(async () => {
  window.addEventListener('beforeunload', beforeUnload)
  await load()
  try { items.value = await authoringApi.items() } catch { /* liste vide */ }
  loadSituations()
})
onBeforeUnmount(() => {
  window.removeEventListener('beforeunload', beforeUnload)
  if (saveState.value === 'dirty') save()
})
</script>

<template>
  <div class="editor-page">
    <Message v-if="loadError" severity="error" :closable="false">{{ loadError }}</Message>

    <template v-if="detail">
      <header class="topbar">
        <Button icon="pi pi-arrow-left" text rounded aria-label="Retour à mes cas" @click="router.push({ name: 'authoring' })" />
        <div class="title-block">
          <h1>{{ title }}</h1>
          <div class="meta">
            <Tag :value="detail.status === 'published' ? 'Publiée' : 'Brouillon'" :severity="detail.status === 'published' ? 'success' : 'secondary'" />
            <Tag v-if="review?.status === 'a_relire'" value="À relire" severity="warn" icon="pi pi-eye" />
            <Tag v-else-if="review?.status === 'relue'" :value="review.changed_since_review ? 'Relue · modifiée depuis' : 'Relue'"
                 :severity="review.changed_since_review ? 'warn' : 'success'" icon="pi pi-check" />
            <span v-if="published.length">version {{ published[0]!.version }} en ligne</span>
            <span class="save-state" :class="saveState">
              <template v-if="saveState === 'saving'"><i class="pi pi-spin pi-spinner"></i> Enregistrement…</template>
              <template v-else-if="saveState === 'dirty'">Modifications en cours…</template>
              <template v-else-if="saveState === 'error'"><i class="pi pi-exclamation-circle"></i> Non enregistré</template>
              <template v-else-if="savedAt">Enregistré à {{ savedAt.toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' }) }}</template>
            </span>
          </div>
        </div>
        <div class="top-actions" v-if="sheet">
          <Button label="Tester le patient" icon="pi pi-comments" severity="secondary" outlined :loading="busy === 'test'"
                  :disabled="busy !== null" @click="testPatient" />
          <Button v-if="canEdit" :label="detail.status === 'published' ? 'Publier une nouvelle version' : 'Publier'" icon="pi pi-send"
                  :loading="busy === 'publish'" :disabled="busy !== null || counts.erreur > 0"
                  :title="counts.erreur ? 'Corrigez d’abord les erreurs' : ''" @click="publish" />
        </div>
      </header>

      <Message v-if="banner" :severity="banner.severity" closable @close="banner = null">{{ banner.text }}</Message>
      <Message v-if="!canEdit" severity="info" :closable="false">
        Station de {{ detail.author }}, en lecture seule pour la relecture. Vous pouvez tester le patient, puis
        laisser une remarque et la marquer comme relue (panneau « Vérifications »).
      </Message>
      <Message v-if="detail.legacy" severity="info" :closable="false">
        Ce cas a été créé avant l'atelier : il n'a pas de fiche structurée et reste modifiable par l'administration.
      </Message>

      <div v-if="sheet" class="layout">
        <!-- ===== Fiche ===== -->
        <main class="sheet">
          <Tabs v-model:value="tab">
            <TabList>
              <Tab value="station">Station</Tab>
              <Tab value="patient">Patient</Tab>
              <Tab value="faits">Ce que sait le patient <span class="count">{{ sheet.facts.length }}</span></Tab>
              <Tab value="examen">Examen clinique</Tab>
              <Tab value="correction">Correction</Tab>
            </TabList>
            <fieldset class="sheet-fieldset" :disabled="!canEdit">
            <TabPanels>
              <!-- Station -->
              <TabPanel value="station">
                <div class="form">
                  <div class="field" data-field="station.title">
                    <label for="title">Titre visible des étudiants</label>
                    <InputText id="title" v-model="sheet.station.title" fluid placeholder="Le motif ou le contexte, sans le diagnostic (ex. « Douleur thoracique aux urgences »)" />
                  </div>
                  <div class="row">
                    <div class="field">
                      <label for="setting">Lieu</label>
                      <InputText id="setting" v-model="sheet.station.setting" fluid placeholder="aux urgences, au cabinet..." />
                    </div>
                    <div class="field">
                      <label for="role">Rôle de l'étudiant</label>
                      <InputText id="role" v-model="sheet.station.student_role" fluid placeholder="l'interne de garde" />
                    </div>
                    <div class="field narrow">
                      <label for="duration">Durée (min)</label>
                      <InputNumber id="duration" v-model="sheet.station.duration_minutes" :min="1" :max="60" show-buttons fluid />
                    </div>
                  </div>
                  <div class="field" data-field="station.student_instructions">
                    <label for="instructions">Consignes données à l'étudiant</label>
                    <Textarea id="instructions" v-model="sheet.station.student_instructions" auto-resize rows="4" fluid
                              placeholder="Ce que l'étudiant lit avant d'entrer : contexte, tâches attendues." />
                  </div>
                  <div class="field" data-field="station.edn_items">
                    <label>Items EDN (R2C)</label>
                    <MultiSelect v-model="sheet.station.edn_items" :options="itemOptions" option-label="label" option-value="value"
                                 filter display="chip" fluid placeholder="Rattachez la station à ses items" empty-message="Aucun item : importez le référentiel" />
                    <small>L'assistant cherche dans le référentiel de ces items.</small>
                  </div>
                  <div class="field">
                    <label>Situations de départ</label>
                    <MultiSelect v-model="sheet.station.starting_situations" :options="situationGroups" option-group-label="label"
                                 option-group-children="items" option-label="label" option-value="value" filter display="chip" fluid
                                 placeholder="Situations de départ couvertes" empty-message="Aucune situation : importez le référentiel" />
                  </div>
                  <div class="field narrow-wide">
                    <label>Voix du patient (mode oral)</label>
                    <Select v-model="sheet.station.voice_id" :options="voiceOptions" option-label="label" option-value="value" fluid />
                  </div>
                </div>
              </TabPanel>

              <!-- Patient -->
              <TabPanel value="patient">
                <div class="form">
                  <div class="row">
                    <div class="field"><label for="fn">Prénom</label><InputText id="fn" v-model="sheet.patient.first_name" fluid /></div>
                    <div class="field"><label for="ln">Nom</label><InputText id="ln" v-model="sheet.patient.last_name" fluid /></div>
                    <div class="field narrow" data-field="patient.age">
                      <label for="age">Âge</label>
                      <InputNumber id="age" v-model="sheet.patient.age" :min="0" :max="120" fluid />
                    </div>
                    <div class="field narrow">
                      <label>Sexe</label>
                      <Select v-model="sheet.patient.sex" :options="SEX" option-label="label" option-value="value" fluid />
                    </div>
                  </div>
                  <div class="row">
                    <div class="field"><label for="occ">Profession</label><InputText id="occ" v-model="sheet.patient.occupation" fluid placeholder="Comptable" /></div>
                    <div class="field"><label for="liv">Situation de vie</label><InputText id="liv" v-model="sheet.patient.living_situation" fluid placeholder="Marié, deux enfants adultes" /></div>
                  </div>
                  <div class="row" data-field="patient.personality">
                    <div class="field">
                      <label for="pers">Caractère</label>
                      <Textarea id="pers" v-model="sheet.patient.personality" auto-resize rows="2" fluid placeholder="Coopératif, pudique, minimise ses symptômes..." />
                    </div>
                    <div class="field">
                      <label for="emo">État au moment de la consultation</label>
                      <Textarea id="emo" v-model="sheet.patient.emotional_state" auto-resize rows="2" fluid placeholder="Inquiet, se tient la poitrine..." />
                    </div>
                  </div>
                  <div class="field narrow-wide">
                    <label>Façon de parler</label>
                    <Select v-model="sheet.patient.language_register" :options="REGISTERS" option-label="label" option-value="value" fluid />
                  </div>
                  <div class="field">
                    <label>Ses inquiétudes</label>
                    <StringList v-model="sheet.patient.concerns" placeholder="Ex. « Est-ce que c'est le cœur ? »" add-label="Ajouter une inquiétude" />
                  </div>
                  <div class="field">
                    <label>Questions qu'il pose de lui-même</label>
                    <StringList v-model="sheet.patient.spontaneous_questions" placeholder="Ex. « Je vais pouvoir rentrer ce soir ? »" add-label="Ajouter une question" />
                  </div>
                  <div class="field">
                    <label>Ses réactions</label>
                    <div v-for="(r, i) in sheet.patient.reactions" :key="i" class="reaction" :class="{ proposed: r.generated }">
                      <InputText v-model="r.when" placeholder="Si l'étudiant… (ex. le rassure)" fluid />
                      <InputText v-model="r.then" placeholder="…il (ex. se détend un peu)" fluid />
                      <Button v-if="r.generated" icon="pi pi-check" text rounded aria-label="Valider" title="Valider la proposition" @click="r.generated = false" />
                      <Button icon="pi pi-times" text rounded severity="secondary" aria-label="Retirer" @click="sheet.patient.reactions.splice(i, 1)" />
                    </div>
                    <Button label="Ajouter une réaction" icon="pi pi-plus" text size="small"
                            @click="sheet.patient.reactions.push({ when: '', then: '', generated: false })" />
                  </div>
                </div>
              </TabPanel>

              <!-- Faits -->
              <TabPanel value="faits">
                <p class="lead" data-field="facts">
                  Écrivez des faits, pas des instructions : ce que le patient sait et comment il le dit. Il ne révèle
                  « seulement si on lui demande » que lorsque l'étudiant pose la question, et répond « je ne sais pas »
                  à ce qui n'est pas dans la fiche.
                </p>
                <FactsEditor v-model="sheet.facts" :issues="issues" />
              </TabPanel>

              <!-- Examen clinique -->
              <TabPanel value="examen">
                <p class="lead">Ce que l'examinateur communique quand l'étudiant examine le patient (outil « examen clinique »).</p>
                <div class="form">
                  <article v-for="(e, i) in sheet.exam_findings" :key="i" class="exam-card" :class="{ proposed: e.generated }">
                    <div class="row">
                      <div class="field"><label>Examen</label><InputText v-model="e.label" fluid placeholder="Auscultation cardiaque" /></div>
                      <div class="field narrow-wide"><label>Identifiant</label><InputText v-model="e.id" fluid placeholder="cardio" /></div>
                      <Button icon="pi pi-trash" text rounded severity="secondary" aria-label="Supprimer" class="end"
                              @click="sheet.exam_findings.splice(i, 1)" />
                    </div>
                    <Textarea v-model="e.findings" auto-resize rows="2" fluid placeholder="Bruits du cœur réguliers, pas de souffle." />
                    <div v-if="e.generated" class="proposed-bar">
                      <Tag severity="warn" value="Proposé par l'assistant · à relire" icon="pi pi-sparkles" />
                      <Button label="Valider" icon="pi pi-check" size="small" text @click="e.generated = false" />
                    </div>
                  </article>
                  <Button label="Ajouter un examen" icon="pi pi-plus" text size="small"
                          @click="sheet.exam_findings.push({ id: '', label: '', findings: '', generated: false })" />
                </div>
              </TabPanel>

              <!-- Correction -->
              <TabPanel value="correction">
                <div class="form">
                  <div class="field" data-field="correction.expected_diagnosis">
                    <label for="dx">Diagnostic attendu</label>
                    <InputText id="dx" v-model="sheet.correction.expected_diagnosis" fluid />
                  </div>
                  <div class="field">
                    <label for="mgmt">Prise en charge attendue</label>
                    <Textarea id="mgmt" v-model="sheet.correction.expected_management" auto-resize rows="2" fluid />
                  </div>
                  <div class="field">
                    <label>Mots que le patient ne prononce jamais</label>
                    <StringList v-model="sheet.never_says" placeholder="Ex. « infarctus »" add-label="Ajouter un mot" />
                    <small>Le diagnostic et les termes qui le trahiraient : ils sont aussi filtrés de ses réponses.</small>
                  </div>
                  <div class="field" data-field="correction.grid">
                    <label>Grille d'évaluation</label>
                    <GridEditor v-model="sheet.correction.grid" :facts="sheet.facts" :issues="issues" />
                  </div>
                </div>
              </TabPanel>
            </TabPanels>
            </fieldset>
          </Tabs>
        </main>

        <!-- ===== Panneau latéral ===== -->
        <aside class="side">
          <Tabs v-model:value="side">
            <TabList>
              <Tab value="checks">Vérifications
                <span v-if="counts.erreur" class="badge danger">{{ counts.erreur }}</span>
                <span v-else-if="counts.attention" class="badge warn">{{ counts.attention }}</span>
              </Tab>
              <Tab v-if="canEdit" value="assistant"><i class="pi pi-sparkles"></i> Générer</Tab>
              <Tab value="preview">Aperçu</Tab>
              <Tab value="corpus">Référentiel</Tab>
            </TabList>
            <TabPanels>
              <TabPanel value="checks">
                <section class="review-box" :class="review?.status || 'none'">
                  <h4><i class="pi pi-eye"></i> Relecture par un collègue</h4>
                  <template v-if="!review?.status">
                    <p class="muted">Facultative : la station reste publiable sans relecture.</p>
                    <Button v-if="canEdit" label="Demander une relecture" icon="pi pi-eye" size="small" outlined
                            :loading="reviewBusy" @click="reviewAction('request')" />
                  </template>
                  <template v-else-if="review.status === 'a_relire'">
                    <p>À relire depuis le {{ fmtDate(review.requested_at) }}. Visible des autres enseignants ; publiable en attendant.</p>
                    <template v-if="detail.can_review">
                      <Textarea v-model="reviewNote" auto-resize rows="3" fluid placeholder="Remarque pour l'auteur (facultative)" />
                      <Button label="Marquer comme relue" icon="pi pi-check" size="small" :loading="reviewBusy" @click="reviewAction('mark')" />
                    </template>
                    <Button v-if="canEdit" label="Retirer la demande" size="small" text severity="secondary"
                            :loading="reviewBusy" @click="reviewAction('clear')" />
                  </template>
                  <template v-else>
                    <p>Relue par <strong>{{ review.reviewer }}</strong> le {{ fmtDate(review.reviewed_at) }}.</p>
                    <blockquote v-if="review.note">{{ review.note }}</blockquote>
                    <p v-if="review.changed_since_review" class="changed">La fiche a été modifiée depuis cette relecture.</p>
                    <div v-if="canEdit" class="review-actions">
                      <Button label="Demander une nouvelle relecture" icon="pi pi-eye" size="small" outlined
                              :loading="reviewBusy" @click="reviewAction('request')" />
                      <Button label="Retirer le statut" size="small" text severity="secondary" @click="reviewAction('clear')" />
                    </div>
                  </template>
                </section>
                <p v-if="!issues.length" class="ok"><i class="pi pi-check-circle"></i> Rien à signaler : la station peut être publiée.</p>
                <p v-if="pendingReview" class="muted">{{ pendingReview }} proposition(s) de l'assistant à relire (badge orange).</p>
                <template v-for="level in (['erreur', 'attention', 'conseil'] as const)" :key="level">
                  <section v-if="counts[level]" class="issue-group">
                    <h4><i :class="LEVEL[level].icon"></i> {{ LEVEL[level].label }}</h4>
                    <button v-for="(issue, k) in issues.filter((i) => i.level === level)" :key="k" type="button"
                            class="issue" :class="level" @click="jump(issue)">{{ issue.message }}</button>
                  </section>
                </template>
              </TabPanel>
              <TabPanel value="assistant">
                <AssistantPanel v-model:sheet="sheet" :case-id="id" @applied="onApplied" />
              </TabPanel>
              <TabPanel value="preview">
                <p class="muted">Ce que reçoit le modèle patient, compilé depuis la fiche (lecture seule).</p>
                <pre class="prompt">{{ detail.preview?.patient_prompt }}</pre>
                <h4>Versions</h4>
                <ul class="versions">
                  <li v-for="v in published" :key="v.id">Version {{ v.version }} publiée le {{ new Date(v.created_at).toLocaleString('fr-FR') }}</li>
                  <li v-if="tests.length" class="muted">{{ tests.length }} test(s) enseignant</li>
                  <li v-if="!published.length && !tests.length" class="muted">Jamais publiée</li>
                </ul>
              </TabPanel>
              <TabPanel value="corpus">
                <CorpusSearch :items="sheet.station.edn_items" />
              </TabPanel>
            </TabPanels>
          </Tabs>
        </aside>
      </div>
    </template>
  </div>
</template>

<style scoped>
.editor-page { height: 100%; overflow-y: auto; padding: 1rem 0 3rem; box-sizing: border-box; }
.topbar { display: flex; align-items: center; gap: 0.75rem; flex-wrap: wrap; margin-bottom: 0.75rem; }
.title-block { flex: 1; min-width: min(16rem, 100%); }
.title-block h1 { font-size: 1.5rem; margin: 0; }
.meta { display: flex; gap: 0.75rem; align-items: center; font-size: 0.85rem; color: #64748b; margin-top: 0.25rem; flex-wrap: wrap; }
.save-state.error { color: #b91c1c; }
.top-actions { display: flex; gap: 0.5rem; flex-wrap: wrap; }
.layout { display: grid; grid-template-columns: minmax(0, 1fr) minmax(20rem, 26rem); gap: 1.25rem; align-items: start; }
.side { position: sticky; top: 0; max-height: calc(100vh - 2rem); overflow-y: auto; border: 1px solid #e2e8f0; border-radius: 12px; }
.side :deep(.p-tab) { padding: 0.75rem 0.6rem; font-size: 0.9rem; }
.side :deep(.p-tabpanels) { padding: 0.9rem; }
.form { display: flex; flex-direction: column; gap: 0.9rem; }
.row { display: flex; gap: 0.75rem; flex-wrap: wrap; align-items: flex-end; }
.row > .field { flex: 1; min-width: min(12rem, 100%); }
.field { display: flex; flex-direction: column; gap: 0.3rem; }
.field label { font-weight: 600; font-size: 0.88rem; color: #334155; }
.field small { color: #64748b; }
.row > .field.narrow { flex: 0 0 8rem; min-width: 8rem; }
.narrow-wide { max-width: 20rem; }
.lead { color: #475569; font-size: 0.92rem; margin: 0 0 1rem; }
.count { margin-left: 0.35rem; font-size: 0.75rem; background: #e2e8f0; border-radius: 999px; padding: 0 0.45rem; }
.reaction { display: flex; gap: 0.4rem; align-items: center; margin-bottom: 0.35rem; }
.reaction.proposed :deep(input) { border-color: #f59e0b; }
.exam-card { border: 1px solid #e2e8f0; border-radius: 10px; padding: 0.75rem; display: flex; flex-direction: column; gap: 0.45rem; }
.exam-card.proposed { border-color: #f59e0b; background: #fffbeb; }
.end { align-self: center; }
.proposed-bar { display: flex; align-items: center; gap: 0.5rem; }
.badge { margin-left: 0.35rem; font-size: 0.75rem; border-radius: 999px; padding: 0 0.45rem; color: #fff; }
.badge.danger { background: #dc2626; }
.badge.warn { background: #d97706; }
.ok { color: #15803d; }
.muted { color: #64748b; font-size: 0.88rem; }
.issue-group h4 { margin: 0.75rem 0 0.35rem; font-size: 0.9rem; }
.issue {
  display: block; width: 100%; text-align: left; font-size: 0.88rem; line-height: 1.35; margin-bottom: 0.35rem;
  padding: 0.45rem 0.6rem; border-radius: 8px; border: 1px solid #e2e8f0; background: #fff; color: #1e293b; font-weight: 400;
}
.issue.erreur { border-left: 4px solid #dc2626; }
.issue.attention { border-left: 4px solid #d97706; }
.issue.conseil { border-left: 4px solid #94a3b8; }
.issue:hover { background: #f8fafc; }
.prompt { white-space: pre-wrap; font-size: 0.82rem; background: #f8fafc; border-radius: 8px; padding: 0.75rem; max-height: 50vh; overflow: auto; }
.versions { padding-left: 1.1rem; font-size: 0.88rem; }
.sheet-fieldset { border: 0; padding: 0; margin: 0; min-width: 0; }
.sheet-fieldset:disabled :deep(.p-select),
.sheet-fieldset:disabled :deep(.p-multiselect) { pointer-events: none; }
.review-box { border: 1px solid #e2e8f0; border-radius: 10px; padding: 0.6rem 0.75rem; margin-bottom: 0.75rem;
  display: flex; flex-direction: column; gap: 0.45rem; align-items: flex-start; }
.review-box.a_relire { border-color: #f59e0b; background: #fffbeb; }
.review-box.relue { border-color: #86efac; background: #f0fdf4; }
.review-box h4 { margin: 0; font-size: 0.9rem; }
.review-box p { margin: 0; font-size: 0.88rem; }
.review-box blockquote { margin: 0; padding: 0.4rem 0.6rem; border-left: 3px solid #94a3b8; background: #fff; font-size: 0.88rem; white-space: pre-line; }
.review-box .changed { color: #b45309; }
.review-actions { display: flex; gap: 0.25rem; flex-wrap: wrap; }
:deep(.flash) { outline: 3px solid #f59e0b; outline-offset: 4px; border-radius: 8px; transition: outline-color 1.5s; }
@media (max-width: 1100px) {
  .layout { grid-template-columns: minmax(0, 1fr); }
  .side { position: static; max-height: none; }
}
</style>
