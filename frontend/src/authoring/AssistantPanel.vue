<script setup lang="ts">
// Bouton « Générer » : l'assistant propose, l'enseignant ajoute ce qu'il retient
import { ref } from 'vue'
import Button from 'primevue/button'
import InputText from 'primevue/inputtext'
import Message from 'primevue/message'
import Tag from 'primevue/tag'
import SourceLinks from './SourceLinks.vue'
import { authoringApi, CATEGORY_LABELS, type AssistTask, type CaseSheet, type Proposal } from './api'
import { errorMessage } from '../services/http'

const sheet = defineModel<CaseSheet>('sheet', { required: true })
const props = defineProps<{ caseId: number }>()
const emit = defineEmits<{ applied: [what: string] }>()

const ACTIONS: { task: AssistTask; label: string; icon: string; help: string }[] = [
  { task: 'interrogatoire', label: 'Compléter l’interrogatoire', icon: 'pi pi-comments',
    help: 'Faits manquants : histoire, antécédents, traitements, mode de vie...' },
  { task: 'negatifs', label: 'Signes négatifs pertinents', icon: 'pi pi-minus-circle',
    help: 'Ce que le patient n’a pas, pour les diagnostics différentiels.' },
  { task: 'langage', label: 'Mots du patient', icon: 'pi pi-user-edit',
    help: 'Reformule les réponses trop techniques ou trop courtes.' },
  { task: 'personnage', label: 'Compléter le personnage', icon: 'pi pi-id-card',
    help: 'Caractère, émotions, inquiétudes, questions, réactions.' },
  { task: 'grille', label: 'Proposer la grille', icon: 'pi pi-list-check',
    help: 'Items d’évaluation reliés aux faits, d’après les objectifs de rang A.' },
  { task: 'examen', label: 'Proposer l’examen clinique', icon: 'pi pi-heart',
    help: 'Ce que l’examinateur répond si l’étudiant examine le patient.' },
]

const instructions = ref('')
const running = ref<AssistTask | null>(null)
const error = ref('')
const proposal = ref<Proposal | null>(null)

async function run(task: AssistTask) {
  running.value = task
  error.value = ''
  try {
    proposal.value = await authoringApi.assist(props.caseId, task, sheet.value, instructions.value)
  } catch (e) {
    error.value = errorMessage(e, 'L’assistant n’a pas pu répondre.')
  } finally {
    running.value = null
  }
}

function factLabel(id: string) {
  const f = sheet.value.facts.find((x) => x.id === id)
  return f ? f.label || f.patient_words.slice(0, 40) : id
}

function addFact(i: number) {
  const p = proposal.value!
  sheet.value.facts.push(p.facts.splice(i, 1)[0]!)
  emit('applied', 'facts')
}
function addAllFacts() {
  const p = proposal.value!
  sheet.value.facts.push(...p.facts.splice(0))
  emit('applied', 'facts')
}
function applyRewrite(i: number) {
  const p = proposal.value!
  const [r] = p.rewrites.splice(i, 1)
  const fact = sheet.value.facts.find((f) => f.id === r!.fact_id)
  if (fact) fact.patient_words = r!.after
  emit('applied', 'facts')
}
function applyPersona() {
  const p = proposal.value!
  const persona = p.persona!
  const target = sheet.value.patient
  if (!target.personality.trim()) target.personality = persona.personality
  if (!target.emotional_state.trim()) target.emotional_state = persona.emotional_state
  target.concerns.push(...persona.concerns.filter((c) => !target.concerns.includes(c)))
  target.spontaneous_questions.push(...persona.spontaneous_questions.filter((q) => !target.spontaneous_questions.includes(q)))
  target.reactions.push(...persona.reactions)
  p.persona = null
  emit('applied', 'patient')
}
function addGrid(i: number) {
  sheet.value.correction.grid.push(proposal.value!.grid.splice(i, 1)[0]!)
  emit('applied', 'correction')
}
function addAllGrid() {
  sheet.value.correction.grid.push(...proposal.value!.grid.splice(0))
  emit('applied', 'correction')
}
function addExam(i: number) {
  sheet.value.exam_findings.push(proposal.value!.exam_findings.splice(i, 1)[0]!)
  emit('applied', 'examen')
}

function isEmpty(p: Proposal) {
  return !p.facts.length && !p.rewrites.length && !p.persona && !p.grid.length && !p.exam_findings.length
}
</script>

<template>
  <div class="assistant">
    <p class="intro">
      L'assistant propose, vous choisissez. Il s'appuie sur le référentiel officiel des items rattachés à la station.
      Ce que vous ajoutez reste marqué <em>à relire</em> jusqu'à votre validation.
    </p>

    <div class="actions">
      <Button v-for="a in ACTIONS" :key="a.task" :icon="a.icon" :label="a.label" severity="secondary" outlined
              :loading="running === a.task" :disabled="running !== null" class="action" :title="a.help"
              @click="run(a.task)" />
    </div>
    <label for="assist-instructions" class="sr-only">Précision pour l'assistant (facultative)</label>
    <InputText id="assist-instructions" v-model="instructions" size="small" fluid placeholder="Précision facultative (ex. « patiente plus âgée, très anxieuse »)" />

    <Message v-if="error" severity="error" :closable="false">{{ error }}</Message>

    <p class="sr-only" role="status">{{ running ? 'Génération en cours, cela peut prendre une à deux minutes…' : '' }}</p>

    <section v-if="proposal" class="proposal">
      <header class="proposal-header">
        <h3>{{ proposal.title }}</h3>
        <Button icon="pi pi-times" text rounded severity="secondary" aria-label="Fermer" @click="proposal = null" />
      </header>

      <p v-if="isEmpty(proposal) && !proposal.notes.length" class="muted">Aucune proposition.</p>

      <!-- Faits -->
      <template v-if="proposal.facts.length">
        <div class="bulk"><Button label="Tout ajouter" icon="pi pi-check-square" size="small" text @click="addAllFacts" /></div>
        <article v-for="(f, i) in proposal.facts" :key="f.id" class="item">
          <div class="item-head">
            <Tag :value="CATEGORY_LABELS[f.category]" severity="secondary" />
            <strong>{{ f.label }}</strong>
          </div>
          <p class="words">« {{ f.patient_words }} »</p>
          <p class="muted small">{{ f.disclosure === 'spontane' ? 'Le dit de lui-même' : `Si on lui demande : ${f.asked_about}` }}</p>
          <SourceLinks :sources="f.sources" />
          <div class="item-actions">
            <Button label="Ajouter" icon="pi pi-plus" size="small" @click="addFact(i)" />
            <Button label="Ignorer" size="small" text severity="secondary" @click="proposal.facts.splice(i, 1)" />
          </div>
        </article>
      </template>

      <!-- Reformulations -->
      <article v-for="(r, i) in proposal.rewrites" :key="r.fact_id" class="item">
        <p class="muted small">{{ factLabel(r.fact_id) }}</p>
        <p class="before">« {{ r.before || '(vide)' }} »</p>
        <p class="words">« {{ r.after }} »</p>
        <div class="item-actions">
          <Button label="Remplacer" icon="pi pi-check" size="small" @click="applyRewrite(i)" />
          <Button label="Ignorer" size="small" text severity="secondary" @click="proposal.rewrites.splice(i, 1)" />
        </div>
      </article>

      <!-- Personnage -->
      <article v-if="proposal.persona" class="item">
        <p><strong>Caractère :</strong> {{ proposal.persona.personality }}</p>
        <p><strong>État :</strong> {{ proposal.persona.emotional_state }}</p>
        <p v-if="proposal.persona.concerns.length"><strong>Inquiétudes :</strong> {{ proposal.persona.concerns.join(' ; ') }}</p>
        <p v-if="proposal.persona.spontaneous_questions.length"><strong>Questions :</strong>
          {{ proposal.persona.spontaneous_questions.join(' ; ') }}</p>
        <ul v-if="proposal.persona.reactions.length" class="reactions">
          <li v-for="(r, k) in proposal.persona.reactions" :key="k">{{ r.when }} → {{ r.then }}</li>
        </ul>
        <p class="muted small">Le caractère et l'état ne remplacent que des champs vides ; le reste s'ajoute.</p>
        <div class="item-actions">
          <Button label="Appliquer" icon="pi pi-check" size="small" @click="applyPersona" />
          <Button label="Ignorer" size="small" text severity="secondary" @click="proposal.persona = null" />
        </div>
      </article>

      <!-- Grille -->
      <template v-if="proposal.grid.length">
        <div class="bulk"><Button label="Tout ajouter" icon="pi pi-check-square" size="small" text @click="addAllGrid" /></div>
        <article v-for="(g, i) in proposal.grid" :key="g.id" class="item">
          <div class="item-head"><strong>{{ g.criterion }}</strong><Tag :value="`${g.points} pt`" severity="info" /></div>
          <p class="small">{{ g.description }}</p>
          <p v-if="g.fact_ids.length" class="muted small">Faits : {{ g.fact_ids.map(factLabel).join(' ; ') }}</p>
          <SourceLinks :sources="g.sources" />
          <div class="item-actions">
            <Button label="Ajouter" icon="pi pi-plus" size="small" @click="addGrid(i)" />
            <Button label="Ignorer" size="small" text severity="secondary" @click="proposal.grid.splice(i, 1)" />
          </div>
        </article>
      </template>

      <!-- Examen clinique -->
      <article v-for="(e, i) in proposal.exam_findings" :key="e.id" class="item">
        <div class="item-head"><strong>{{ e.label }}</strong></div>
        <p class="small">{{ e.findings }}</p>
        <div class="item-actions">
          <Button label="Ajouter" icon="pi pi-plus" size="small" @click="addExam(i)" />
          <Button label="Ignorer" size="small" text severity="secondary" @click="proposal.exam_findings.splice(i, 1)" />
        </div>
      </article>

      <ul v-if="proposal.notes.length" class="notes">
        <li v-for="(n, i) in proposal.notes" :key="i">{{ n }}</li>
      </ul>
      <details v-if="proposal.sources.length" class="consulted">
        <summary>Extraits du référentiel consultés ({{ proposal.sources.length }})</summary>
        <SourceLinks :sources="proposal.sources" />
      </details>
    </section>
  </div>
</template>

<style scoped>
.assistant { display: flex; flex-direction: column; gap: 0.75rem; }
.intro { margin: 0; font-size: 0.9rem; color: #475569; }
.actions { display: grid; grid-template-columns: repeat(auto-fill, minmax(13rem, 1fr)); gap: 0.4rem; }
.action { justify-content: flex-start; }
.proposal { border-top: 1px solid #e2e8f0; padding-top: 0.5rem; display: flex; flex-direction: column; gap: 0.5rem; }
.proposal-header { display: flex; justify-content: space-between; align-items: center; }
.proposal-header h3 { margin: 0; font-size: 1rem; }
.bulk { display: flex; justify-content: flex-end; }
.item { border: 1px solid #e2e8f0; border-radius: 10px; padding: 0.6rem 0.75rem; display: flex; flex-direction: column; gap: 0.3rem; }
.item p { margin: 0; }
.item-head { display: flex; gap: 0.5rem; align-items: center; flex-wrap: wrap; }
.item-actions { display: flex; gap: 0.25rem; }
.words { font-style: italic; color: #1e293b; }
.before { color: #64748b; text-decoration: line-through; }
.muted { color: #64748b; }
.small { font-size: 0.85rem; }
.reactions { margin: 0; padding-left: 1.1rem; font-size: 0.9rem; }
.notes { margin: 0; padding-left: 1.1rem; font-size: 0.85rem; color: #64748b; }
.consulted summary { cursor: pointer; font-size: 0.85rem; color: #475569; }
</style>
