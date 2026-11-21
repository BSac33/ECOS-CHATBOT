<script setup lang="ts">
// Échelles d'attitude (0 à 4) et évaluation globale de la performance
import { computed } from 'vue'
import Checkbox from 'primevue/checkbox'
import InputNumber from 'primevue/inputnumber'
import Textarea from 'primevue/textarea'
import ToggleSwitch from 'primevue/toggleswitch'
import { LEVEL_NAMES, STANDARD_SCALES, type CaseSheet } from './api'

const correction = defineModel<CaseSheet['correction']>({ required: true })

const selected = computed(() => new Set(correction.value.scales.map((s) => s.id)))
const weightPercent = computed({
  get: () => Math.round(correction.value.attitude_weight * 100),
  set: (v: number | null) => { correction.value.attitude_weight = (v ?? 0) / 100 },
})

function toggle(id: string, on: boolean) {
  if (on && !selected.value.has(id)) {
    correction.value.scales.push({ id, label: STANDARD_SCALES[id]!, levels: [], observable: id !== 'non_verbale' })
  } else if (!on) {
    correction.value.scales = correction.value.scales.filter((s) => s.id !== id)
  }
}
function scale(id: string) {
  return correction.value.scales.find((s) => s.id === id)!
}
function customize(id: string) {
  const sc = scale(id)
  if (sc.levels.length !== 5) sc.levels = ['', '', '', '', '']
}
</script>

<template>
  <div class="scales-editor">
    <p class="hint">
      Cochées par l'évaluateur de 0 (inacceptable) à 4 (remarquable). Elles comptent pour
      <InputNumber v-model="weightPercent" :min="0" :max="50" suffix=" %" input-class="weight"
                   aria-label="Part des échelles d’attitude dans la note, en pourcentage" /> de la note /20
      (ECOS nationaux : 20 à 30 %).
    </p>
    <div class="scale-list">
      <div v-for="(label, id) in STANDARD_SCALES" :key="id" class="scale-row" :class="{ on: selected.has(id) }">
        <label class="scale-check">
          <Checkbox :model-value="selected.has(id)" binary @update:model-value="toggle(id, $event)" />
          <span>{{ label }}</span>
          <small v-if="id === 'non_verbale'" class="muted">(affichée, non notée sur la plateforme)</small>
        </label>
        <details v-if="selected.has(id)" class="levels">
          <summary @click="customize(id)">Descripteurs des niveaux {{ scale(id).levels.length === 5 ? '' : '(génériques)' }}</summary>
          <div v-for="(name, level) in LEVEL_NAMES" :key="level" class="level">
            <span class="level-name">{{ level }} · {{ name }}</span>
            <Textarea v-if="scale(id).levels.length === 5" v-model="scale(id).levels[level]" auto-resize rows="1" fluid />
          </div>
        </details>
      </div>
    </div>
    <label class="global">
      <ToggleSwitch v-model="correction.global_rating" />
      Évaluation globale de la performance (0 à 4, indicative, hors note)
    </label>
  </div>
</template>

<style scoped>
.scales-editor { display: flex; flex-direction: column; gap: 0.6rem; }
.hint { margin: 0; color: #475569; font-size: 0.9rem; display: flex; align-items: center; gap: 0.35rem; flex-wrap: wrap; }
.hint :deep(.weight) { width: 4.5rem; }
.scale-list { display: grid; grid-template-columns: repeat(auto-fill, minmax(20rem, 1fr)); gap: 0.4rem; }
.scale-row { border: 1px solid #e2e8f0; border-radius: 8px; padding: 0.45rem 0.6rem; }
.scale-row.on { border-color: #10b981; background: #f0fdf4; }
.scale-check { display: flex; gap: 0.5rem; align-items: center; cursor: pointer; font-size: 0.92rem; flex-wrap: wrap; }
.muted { color: #64748b; }
.levels { margin-top: 0.4rem; }
.levels summary { cursor: pointer; font-size: 0.85rem; color: #475569; }
.level { display: flex; flex-direction: column; gap: 0.2rem; margin-top: 0.35rem; }
.level-name { font-size: 0.8rem; font-weight: 600; color: #334155; }
.global { display: flex; gap: 0.5rem; align-items: center; font-size: 0.92rem; color: #334155; }
</style>
