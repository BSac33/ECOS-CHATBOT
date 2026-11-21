<template>
  <article class="evaluation-item" :class="{ validated: item.is_validated }">
    <div class="evaluation-item-header">
      <div class="icon-container" aria-hidden="true">
        <svg v-if="item.is_validated" class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3">
          <polyline points="20 6 9 17 4 12"></polyline>
        </svg>
        <svg v-else class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3">
          <line x1="18" y1="6" x2="6" y2="18"></line>
          <line x1="6" y1="6" x2="18" y2="18"></line>
        </svg>
      </div>
      <div class="item-info">
        <h3 class="item-title">{{ item.criterion }}</h3>
        <div class="item-status">
          <!-- Statut en texte : pas seulement l'icône et la couleur -->
          <span class="status-text">{{ item.is_validated ? 'Critère validé' : 'Critère non validé' }}</span>
          <span class="item-score">
            <span class="points-obtained">{{ fmt(item.points_awarded) }}</span>
            <span class="separator" aria-hidden="true">/</span>
            <span class="sr-only"> sur </span>
            <span class="points-possible">{{ fmt(item.points_possible) }}</span>
            <span class="points-label">{{ item.points_possible > 1 ? 'points' : 'point' }}</span>
          </span>
          <span v-if="item.overridden" class="overridden">
            <i class="pi pi-user-edit" aria-hidden="true"></i> modifié par l'enseignant
          </span>
        </div>
      </div>
    </div>
    <p class="justification">{{ item.justification }}</p>
    <blockquote v-if="item.citation" class="citation">
      <span class="citation-label">Extrait de votre passage :</span>
      « {{ item.citation }} »
    </blockquote>
    <p v-if="item.citation && item.citation_found === false" class="citation-warning">
      <i class="pi pi-info-circle" aria-hidden="true"></i>
      Cet extrait n'a pas été retrouvé mot pour mot dans la transcription : il peut être reformulé.
    </p>
  </article>
</template>

<script setup lang="ts">
import type { EvaluationItemResult } from '../types';

defineProps<{ item: EvaluationItemResult }>();

function fmt(value: number): string {
  return (Math.round(value * 100) / 100).toLocaleString('fr-FR');
}
</script>

<style scoped>
.evaluation-item {
  background: white;
  border: 2px solid #b91c1c;
  border-radius: 12px;
  padding: 20px;
  background: linear-gradient(to right, #fef2f2 0%, white 50%);
}

.evaluation-item.validated {
  border-color: #047857;
  background: linear-gradient(to right, #f0fdf4 0%, white 50%);
}

.evaluation-item-header {
  display: flex;
  align-items: flex-start;
  gap: 16px;
  margin-bottom: 12px;
}

.icon-container {
  flex-shrink: 0;
  width: 40px;
  height: 40px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #b91c1c;
}

.validated .icon-container {
  background: #047857;
}

.icon {
  width: 24px;
  height: 24px;
  color: white;
}

.item-info {
  flex: 1;
  min-width: 0;
}

.item-title {
  font-size: 1.1rem;
  font-weight: 600;
  color: #1f2937;
  margin: 0 0 8px 0;
  line-height: 1.4;
}

.item-status {
  display: flex;
  align-items: baseline;
  flex-wrap: wrap;
  gap: 0.25rem 1rem;
}

.status-text {
  font-weight: 700;
  color: #991b1b;
}

.validated .status-text {
  color: #065f46;
}

.item-score {
  display: inline-flex;
  align-items: baseline;
  gap: 4px;
  font-size: 16px;
}

.points-obtained {
  font-size: 22px;
  font-weight: 700;
  color: #991b1b;
}

.validated .points-obtained {
  color: #065f46;
}

.separator {
  font-size: 18px;
  color: #4b5563;
  margin: 0 2px;
}

.points-possible {
  font-size: 18px;
  font-weight: 600;
  color: #4b5563;
}

.points-label {
  font-size: 14px;
  color: #4b5563;
  margin-left: 4px;
}

.overridden {
  font-size: 0.85rem;
  color: #3730a3;
  font-weight: 600;
}

.justification {
  margin: 0;
  padding: 16px;
  background: #f9fafb;
  border-left: 4px solid #b91c1c;
  border-radius: 6px;
  font-size: 15px;
  line-height: 1.6;
  color: #374151;
}

.validated .justification {
  border-left-color: #047857;
  background: #f0fdf4;
}

.citation {
  margin: 0.75rem 0 0;
  padding: 0.5rem 0.75rem;
  border-left: 3px solid #64748b;
  color: #374151;
  font-style: italic;
  font-size: 0.92rem;
}

.citation-label {
  display: block;
  font-style: normal;
  font-weight: 600;
  font-size: 0.8rem;
  color: #4b5563;
}

.citation-warning {
  margin: 0.35rem 0 0;
  font-size: 0.82rem;
  color: #4b5563;
}
</style>
