<script setup lang="ts">
// Liste de courts textes éditables (inquiétudes, questions, termes interdits)
import InputText from 'primevue/inputtext'
import Button from 'primevue/button'

const items = defineModel<string[]>({ required: true })
defineProps<{ placeholder?: string; addLabel?: string }>()

function add() {
  items.value.push('')
}
function remove(i: number) {
  items.value.splice(i, 1)
}
</script>

<template>
  <div class="string-list">
    <div v-for="(_, i) in items" :key="i" class="string-row">
      <InputText v-model="items[i]" :placeholder="placeholder" fluid />
      <Button icon="pi pi-times" text rounded severity="secondary" aria-label="Retirer" @click="remove(i)" />
    </div>
    <Button :label="addLabel || 'Ajouter'" icon="pi pi-plus" text size="small" @click="add" />
  </div>
</template>

<style scoped>
.string-list { display: flex; flex-direction: column; gap: 0.4rem; align-items: flex-start; }
.string-row { display: flex; gap: 0.25rem; width: 100%; align-items: center; }
</style>
