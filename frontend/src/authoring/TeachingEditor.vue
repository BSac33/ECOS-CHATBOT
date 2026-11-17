<script setup lang="ts">
// Contenu pédagogique montré à l'étudiant au débriefing (après la correction)
import InputText from 'primevue/inputtext'
import Textarea from 'primevue/textarea'
import Button from 'primevue/button'
import StringList from './StringList.vue'
import type { TeachingContent } from './api'

const teaching = defineModel<TeachingContent>({ required: true })
</script>

<template>
  <div class="form">
    <p class="lead">Montré à l'étudiant au débriefing, après la correction (jamais pendant la station).</p>
    <div class="field">
      <label>Objectifs pédagogiques</label>
      <StringList v-model="teaching.objectives" placeholder="Ex. « D'analyser un ECG selon une méthode systématique »" add-label="Ajouter un objectif" />
    </div>
    <div class="field">
      <label>Éléments clés de l'évaluation</label>
      <div v-for="(k, i) in teaching.key_points" :key="i" class="key-row">
        <InputText v-model="k.label" placeholder="Rubrique" class="key-label" />
        <Textarea v-model="k.text" auto-resize rows="1" placeholder="Ce qui est attendu" class="key-text" />
        <Button icon="pi pi-times" text rounded severity="secondary" aria-label="Retirer" @click="teaching.key_points.splice(i, 1)" />
      </div>
      <Button label="Ajouter un élément clé" icon="pi pi-plus" text size="small"
              @click="teaching.key_points.push({ label: '', text: '' })" />
    </div>
    <div class="field">
      <label for="script">Proposition de script</label>
      <Textarea id="script" v-model="teaching.model_script" auto-resize rows="6" fluid />
    </div>
    <div class="field">
      <label for="comments">Commentaires pédagogiques</label>
      <Textarea id="comments" v-model="teaching.comments" auto-resize rows="8" fluid />
    </div>
  </div>
</template>

<style scoped>
.form { display: flex; flex-direction: column; gap: 0.9rem; }
.field { display: flex; flex-direction: column; gap: 0.3rem; }
.field > label { font-weight: 600; font-size: 0.88rem; color: #334155; }
.lead { color: #475569; font-size: 0.92rem; margin: 0; }
.key-row { display: flex; gap: 0.4rem; align-items: flex-start; margin-bottom: 0.35rem; }
.key-label { width: 14rem; flex-shrink: 0; }
.key-text { flex: 1; }
@media (max-width: 720px) { .key-row { flex-wrap: wrap; } .key-label { width: 100%; } }
</style>
