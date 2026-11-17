<script setup lang="ts">
// Grille d'évaluation : chaque item est relié aux faits que l'étudiant doit obtenir
import { computed } from 'vue'
import InputText from 'primevue/inputtext'
import InputNumber from 'primevue/inputnumber'
import Textarea from 'primevue/textarea'
import MultiSelect from 'primevue/multiselect'
import Button from 'primevue/button'
import Tag from 'primevue/tag'
import SourceLinks from './SourceLinks.vue'
import { CATEGORY_LABELS, emptyGridItem, type Fact, type GridItem, type Issue } from './api'

const grid = defineModel<GridItem[]>({ required: true })
const props = defineProps<{ facts: Fact[]; issues: Issue[] }>()

const factOptions = computed(() =>
  props.facts.map((f) => ({
    value: f.id,
    label: f.label || f.patient_words.slice(0, 60) || 'Fait sans libellé',
    group: CATEGORY_LABELS[f.category],
  })),
)
const total = computed(() => grid.value.reduce((sum, g) => sum + (Number(g.points) || 0), 0))

function issuesFor(index: number) {
  return props.issues.filter((i) => i.field === `correction.grid[${index}]`)
}
function move(index: number, delta: number) {
  const target = index + delta
  if (target < 0 || target >= grid.value.length) return
  const [item] = grid.value.splice(index, 1)
  grid.value.splice(target, 0, item!)
}
</script>

<template>
  <div class="grid-editor">
    <article v-for="(item, index) in grid" :key="item.id" class="grid-card" :class="{ proposed: item.generated }"
             :data-field="`correction.grid[${index}]`">
      <div class="grid-top">
        <span class="grid-number">{{ index + 1 }}</span>
        <InputText v-model="item.criterion" placeholder="Critère observable (ex. « Recherche le tabagisme »)" fluid class="criterion" />
        <InputNumber v-model="item.points" :min="0" :max="20" :step="0.5" show-buttons :min-fraction-digits="0"
                     :max-fraction-digits="1" suffix=" pt" class="points" aria-label="Points" />
        <Button icon="pi pi-arrow-up" text rounded severity="secondary" aria-label="Monter" :disabled="index === 0" @click="move(index, -1)" />
        <Button icon="pi pi-arrow-down" text rounded severity="secondary" aria-label="Descendre"
                :disabled="index === grid.length - 1" @click="move(index, 1)" />
        <Button icon="pi pi-trash" text rounded severity="secondary" aria-label="Supprimer l'item" @click="grid.splice(index, 1)" />
      </div>
      <Textarea v-model="item.description" auto-resize rows="1" fluid
                placeholder="Comment l'attribuer (ex. « Tabac + quantité = 1 pt ; tabac seul = 0,5 pt »)" />
      <MultiSelect v-if="facts.length" v-model="item.fact_ids" :options="factOptions" option-label="label" option-value="value"
                   display="chip" filter placeholder="Faits que l'étudiant doit obtenir pour valider l'item" fluid
                   :max-selected-labels="6" />
      <div v-if="item.generated" class="proposed-bar">
        <Tag severity="warn" value="Proposé par l'assistant · à relire" icon="pi pi-sparkles" />
        <Button label="Valider" icon="pi pi-check" size="small" text @click="item.generated = false" />
      </div>
      <SourceLinks :sources="item.sources" />
      <p v-for="(issue, k) in issuesFor(index)" :key="k" class="inline-issue" :class="issue.level">{{ issue.message }}</p>
    </article>

    <div class="grid-footer">
      <Button label="Ajouter un item" icon="pi pi-plus" text size="small" @click="grid.push(emptyGridItem())" />
      <span class="total">Total : <strong>{{ total }}</strong> points</span>
    </div>
  </div>
</template>

<style scoped>
.grid-editor { display: flex; flex-direction: column; gap: 0.6rem; }
.grid-card {
  border: 1px solid #e2e8f0; border-radius: 10px; padding: 0.75rem;
  display: flex; flex-direction: column; gap: 0.45rem; background: #fff;
}
.grid-card.proposed { border-color: #f59e0b; background: #fffbeb; }
.grid-top { display: flex; gap: 0.35rem; align-items: center; }
.grid-number { width: 1.75rem; text-align: center; font-weight: 700; color: #64748b; flex-shrink: 0; }
.criterion { flex: 1; }
.grid-top :deep(.points) { width: 7rem; flex-shrink: 0; }
.grid-top :deep(.points input) { width: 100%; min-width: 0; }
.proposed-bar { display: flex; align-items: center; gap: 0.5rem; }
.grid-footer { display: flex; justify-content: space-between; align-items: center; }
.total { color: #334155; }
.inline-issue { margin: 0; font-size: 0.85rem; }
.inline-issue.erreur { color: #b91c1c; }
.inline-issue.attention { color: #b45309; }
.inline-issue.conseil { color: #475569; }
@media (max-width: 720px) { .grid-top { flex-wrap: wrap; } }
</style>
