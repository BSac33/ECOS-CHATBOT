<script setup lang="ts">
// Faits du cas, groupés par catégorie : ce que sait le patient et comment il le dit
import { computed } from 'vue'
import InputText from 'primevue/inputtext'
import Textarea from 'primevue/textarea'
import Select from 'primevue/select'
import SelectButton from 'primevue/selectbutton'
import Button from 'primevue/button'
import Tag from 'primevue/tag'
import SourceLinks from './SourceLinks.vue'
import { CATEGORY_LABELS, CATEGORY_ORDER, emptyFact, type Fact, type FactCategory, type Issue } from './api'

const facts = defineModel<Fact[]>({ required: true })
const props = defineProps<{ issues: Issue[] }>()

const HINTS: Record<FactCategory, string> = {
  motif: 'Ce qui amène le patient, tel qu’il le dit en entrant. Ex. « J’ai mal à la poitrine depuis ce matin. »',
  histoire: 'Début, siège, type, intensité, évolution... Ex. « Ça me serre, comme un étau. »',
  symptome: 'Ce qui accompagne le motif. Ex. « J’ai beaucoup transpiré. »',
  signe_negatif: 'Ce qu’il n’a pas et qu’il faut rechercher. Ex. « Non, je respire normalement. »',
  antecedent: 'Maladies, opérations, histoire familiale.',
  traitement: 'Médicaments, avec les mots du patient (« un cachet pour la tension »).',
  allergie: 'Même s’il n’en a pas : sinon le patient risque d’inventer.',
  mode_de_vie: 'Tabac, alcool, activité physique, alimentation.',
  contexte: 'Travail, famille, événements récents.',
  autre: 'Tout autre élément utile au jeu.',
}

const categoryOptions = CATEGORY_ORDER.map((c) => ({ value: c, label: CATEGORY_LABELS[c] }))
const disclosureOptions = [
  { value: 'spontane', label: 'Le dit de lui-même' },
  { value: 'sur_question', label: 'Seulement si on lui demande' },
]

const groups = computed(() =>
  CATEGORY_ORDER.map((category) => ({
    category,
    entries: facts.value.map((fact, index) => ({ fact, index })).filter((e) => e.fact.category === category),
  })),
)

function issuesFor(index: number) {
  return props.issues.filter((i) => i.field === `facts[${index}]`)
}

function add(category: FactCategory) {
  facts.value.push(emptyFact(category))
}
function remove(index: number) {
  facts.value.splice(index, 1)
}
</script>

<template>
  <div class="facts">
    <section v-for="group in groups" :key="group.category" class="fact-group">
      <header class="group-header">
        <h3>{{ CATEGORY_LABELS[group.category] }}</h3>
        <span v-if="!group.entries.length" class="hint">{{ HINTS[group.category] }}</span>
      </header>

      <article
        v-for="{ fact, index } in group.entries"
        :key="fact.id"
        class="fact-card"
        :class="{ proposed: fact.generated }"
        :data-field="`facts[${index}]`"
      >
        <div class="fact-top">
          <InputText v-model="fact.label" placeholder="Note médicale (pour vous et l'évaluateur)" class="fact-label" fluid />
          <Select v-model="fact.category" :options="categoryOptions" option-label="label" option-value="value" class="fact-category" />
          <Button icon="pi pi-trash" text rounded severity="secondary" aria-label="Supprimer le fait" @click="remove(index)" />
        </div>

        <label class="field-label" :for="`words-${fact.id}`">Ce que dit le patient</label>
        <Textarea :id="`words-${fact.id}`" v-model="fact.patient_words" auto-resize rows="2" fluid
                  :placeholder="HINTS[fact.category]" />

        <div class="fact-bottom">
          <SelectButton v-model="fact.disclosure" :options="disclosureOptions" option-label="label" option-value="value"
                        :allow-empty="false" size="small" />
          <InputText v-if="fact.disclosure === 'sur_question'" v-model="fact.asked_about" size="small" class="asked-about"
                     placeholder="Sujet de la question (ex. « le tabac »)" />
        </div>

        <div v-if="fact.generated" class="proposed-bar">
          <Tag severity="warn" value="Proposé par l'assistant · à relire" icon="pi pi-sparkles" />
          <Button label="Valider" icon="pi pi-check" size="small" text @click="fact.generated = false" />
        </div>
        <SourceLinks :sources="fact.sources" />
        <p v-for="(issue, k) in issuesFor(index)" :key="k" class="inline-issue" :class="issue.level">{{ issue.message }}</p>
      </article>

      <Button :label="`Ajouter : ${CATEGORY_LABELS[group.category].toLowerCase()}`" icon="pi pi-plus" text size="small"
              @click="add(group.category)" />
    </section>
  </div>
</template>

<style scoped>
.facts { display: flex; flex-direction: column; gap: 1.25rem; }
.group-header { display: flex; flex-direction: column; gap: 0.15rem; margin-bottom: 0.4rem; }
.group-header h3 { margin: 0; font-size: 1rem; color: #1e293b; }
.hint { font-size: 0.85rem; color: #64748b; }
.fact-card {
  border: 1px solid #e2e8f0; border-radius: 10px; padding: 0.75rem; margin-bottom: 0.5rem;
  display: flex; flex-direction: column; gap: 0.45rem; background: #fff;
}
.fact-card.proposed { border-color: #f59e0b; background: #fffbeb; }
.fact-top { display: flex; gap: 0.5rem; align-items: center; }
.fact-label { flex: 1; }
.fact-category { width: 14rem; flex-shrink: 0; }
.field-label { font-size: 0.8rem; color: #475569; font-weight: 600; }
.fact-bottom { display: flex; gap: 0.5rem; flex-wrap: wrap; align-items: center; }
.asked-about { flex: 1; min-width: 14rem; }
.proposed-bar { display: flex; align-items: center; gap: 0.5rem; }
.inline-issue { margin: 0; font-size: 0.85rem; }
.inline-issue.erreur { color: #b91c1c; }
.inline-issue.attention { color: #b45309; }
.inline-issue.conseil { color: #475569; }
@media (max-width: 720px) {
  .fact-top { flex-wrap: wrap; }
  .fact-category { width: 100%; }
}
</style>
