<template>
  <div class="chat-header">
    <div class="header-content">
      <div class="case-title">
        <i class="pi pi-file-medical"></i>
        <h2>{{ caseTitle }}</h2>
      </div>
      
      <div class="time-section">
        <div 
          class="timer"
          :class="timerClass"
        >
          <i class="pi pi-clock"></i>
          <span class="time">{{ formattedTime }}</span>
        </div>
        <Button
          v-if="!isExpired"
          icon="pi pi-times"
          label="Quitter"
          severity="secondary"
          size="small"
          @click="handleQuit"
        />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue';
import { useAttemptStore } from '../stores/attempt';
import Button from 'primevue/button';

const attemptStore = useAttemptStore();
const syncInterval = ref<number | null>(null);
const countdownInterval = ref<number | null>(null);

const caseTitle = computed(() => attemptStore.currentCase?.title || 'Cas clinique');
const isExpired = computed(() => attemptStore.isExpired);

const formattedTime = computed(() => {
  const seconds = attemptStore.timeRemaining;
  
  if (seconds === null) return '--:--';
  if (seconds <= 0) return '00:00';
  
  const mins = Math.floor(seconds / 60);
  const secs = seconds % 60;
  
  return `${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;
});

const timerClass = computed(() => {
  const seconds = attemptStore.timeRemaining;
  
  if (seconds === null) return '';
  if (isExpired.value || seconds === 0) return 'timer-expired';
  if (seconds <= 60) return 'timer-critical';
  if (seconds <= 120) return 'timer-warning';
  
  return 'timer-normal';
});

const emit = defineEmits<{
  quit: [];
}>();

function handleQuit() {
  if (confirm('Êtes-vous sûr de vouloir quitter ? Votre progression sera sauvegardée.')) {
    emit('quit');
  }
}

onMounted(() => {
  // Attendre que le timer soit démarré avant de lancer les intervals
  const checkTimer = setInterval(() => {
    if (attemptStore.isTimerStarted) {
      clearInterval(checkTimer);
      
      // Décrémenter le temps localement chaque seconde pour la fluidité
      countdownInterval.value = window.setInterval(() => {
        attemptStore.decrementLocalTime();
      }, 1000);
      
      // Synchroniser avec le backend toutes les 10 secondes
      syncInterval.value = window.setInterval(() => {
        attemptStore.syncTimeRemaining();
      }, 10000);
    }
  }, 100);
});

onUnmounted(() => {
  if (countdownInterval.value) {
    clearInterval(countdownInterval.value);
  }
  if (syncInterval.value) {
    clearInterval(syncInterval.value);
  }
});
</script>

<style scoped>
.chat-header {
  position: sticky;
  top: 0;
  z-index: 100;
  background: white;
  border-bottom: 2px solid #e0e0e0;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
}

.header-content {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 1rem 2rem;
  max-width: 95%;
  margin: 0 auto;
}

@media (min-width: 1920px) {
  .header-content {
    max-width: 1800px;
  }
}

.case-title {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.case-title i {
  font-size: 1.5rem;
  color: #667eea;
}

.case-title h2 {
  margin: 0;
  font-size: 1.25rem;
  color: #333;
  font-weight: 600;
}

.time-section {
  display: flex;
  align-items: center;
  gap: 1rem;
}

.timer {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.5rem 1rem;
  border-radius: 8px;
  font-weight: 600;
  font-size: 1.1rem;
  transition: all 0.3s ease;
}

.timer i {
  font-size: 1.25rem;
}

.timer-normal {
  background: #d4edda;
  color: #155724;
}

.timer-warning {
  background: #fff3cd;
  color: #856404;
  animation: pulse-warning 2s infinite;
}

.timer-critical {
  background: #f8d7da;
  color: #721c24;
  animation: pulse-critical 1s infinite;
}

.timer-expired {
  background: #dc3545;
  color: white;
  animation: pulse-expired 0.5s infinite;
}

@keyframes pulse-warning {
  0%, 100% {
    transform: scale(1);
  }
  50% {
    transform: scale(1.05);
  }
}

@keyframes pulse-critical {
  0%, 100% {
    transform: scale(1);
  }
  50% {
    transform: scale(1.08);
  }
}

@keyframes pulse-expired {
  0%, 100% {
    opacity: 1;
  }
  50% {
    opacity: 0.7;
  }
}

.time {
  font-family: 'Courier New', monospace;
  letter-spacing: 1px;
}
</style>
