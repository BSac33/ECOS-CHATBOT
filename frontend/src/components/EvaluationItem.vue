<template>
  <div class="evaluation-item" :class="{ 'validated': isValidated }">
    <div class="evaluation-item-header">
      <div class="icon-container">
        <svg v-if="isValidated" class="icon icon-check" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <polyline points="20 6 9 17 4 12"></polyline>
        </svg>
        <svg v-else class="icon icon-cross" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <line x1="18" y1="6" x2="6" y2="18"></line>
          <line x1="6" y1="6" x2="18" y2="18"></line>
        </svg>
      </div>
      <div class="item-info">
        <h3 class="item-title">{{ item.item_name }}</h3>
        <div class="item-score">
          <span class="points-obtained">{{ item.points_obtained }}</span>
          <span class="separator">/</span>
          <span class="points-possible">{{ item.points_possible }}</span>
          <span class="points-label">points</span>
        </div>
      </div>
    </div>
    <blockquote class="justification">
      {{ item.justification }}
    </blockquote>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';

interface EvaluationItemProps {
  item: {
    edn_code?: string;
    item_name: string;
    points_obtained: number;
    points_possible: number;
    justification: string;
  };
}

const props = defineProps<EvaluationItemProps>();

// Un item est considéré comme validé si au moins 50% des points sont obtenus
const isValidated = computed(() => {
  if (props.item.points_possible === 0) return false;
  return props.item.points_obtained / props.item.points_possible >= 0.5;
});
</script>

<style scoped>
.evaluation-item {
  background: white;
  border: 2px solid #e5e7eb;
  border-radius: 12px;
  padding: 20px;
  margin-bottom: 16px;
  transition: all 0.2s ease;
}

.evaluation-item:hover {
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
}

.evaluation-item.validated {
  border-color: #10b981;
  background: linear-gradient(to right, #f0fdf4 0%, white 50%);
}

.evaluation-item:not(.validated) {
  border-color: #ef4444;
  background: linear-gradient(to right, #fef2f2 0%, white 50%);
}

.evaluation-item-header {
  display: flex;
  align-items: flex-start;
  gap: 16px;
  margin-bottom: 16px;
}

.icon-container {
  flex-shrink: 0;
  width: 40px;
  height: 40px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
}

.validated .icon-container {
  background: #10b981;
}

.evaluation-item:not(.validated) .icon-container {
  background: #ef4444;
}

.icon {
  width: 24px;
  height: 24px;
  color: white;
}

.icon-check {
  stroke-width: 3;
}

.icon-cross {
  stroke-width: 3;
}

.item-info {
  flex: 1;
}

.item-title {
  font-size: 18px;
  font-weight: 600;
  color: #1f2937;
  margin: 0 0 8px 0;
  line-height: 1.4;
}

.item-score {
  display: flex;
  align-items: baseline;
  gap: 4px;
  font-size: 16px;
}

.points-obtained {
  font-size: 24px;
  font-weight: 700;
  color: #1f2937;
}

.validated .points-obtained {
  color: #10b981;
}

.evaluation-item:not(.validated) .points-obtained {
  color: #ef4444;
}

.separator {
  font-size: 20px;
  color: #9ca3af;
  margin: 0 2px;
}

.points-possible {
  font-size: 20px;
  font-weight: 600;
  color: #6b7280;
}

.points-label {
  font-size: 14px;
  color: #9ca3af;
  margin-left: 4px;
}

.justification {
  margin: 0;
  padding: 16px;
  background: #f9fafb;
  border-left: 4px solid #d1d5db;
  border-radius: 6px;
  font-size: 15px;
  line-height: 1.6;
  color: #4b5563;
  font-style: italic;
}

.validated .justification {
  border-left-color: #10b981;
  background: #f0fdf4;
}

.evaluation-item:not(.validated) .justification {
  border-left-color: #ef4444;
  background: #fef2f2;
}
</style>
