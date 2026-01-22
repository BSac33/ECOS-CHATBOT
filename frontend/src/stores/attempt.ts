import { defineStore } from 'pinia';
import { ref, computed } from 'vue';
import { apiService, type Attempt, type ClinicalCase } from '../services/api';

export const useAttemptStore = defineStore('attempt', () => {
  const currentAttempt = ref<Attempt | null>(null);
  const currentCase = ref<ClinicalCase | null>(null);
  const timeRemaining = ref<number | null>(null);
  const isExpired = ref(false);
  const loading = ref(false);
  const error = ref<string | null>(null);
  const isTimerStarted = ref(false);

  const hasActiveAttempt = computed(() => currentAttempt.value !== null);
  const durationSeconds = computed(() => currentCase.value?.duration_seconds || 0);

  function selectCase(clinicalCase: ClinicalCase) {
    currentCase.value = clinicalCase;
    // Réinitialiser l'état
    currentAttempt.value = null;
    timeRemaining.value = null;
    isExpired.value = false;
    isTimerStarted.value = false;
    error.value = null;
  }

  async function createAttempt(caseId: number) {
    loading.value = true;
    error.value = null;

    try {
      // Récupérer les infos du cas (déjà chargé normalement)
      if (!currentCase.value) {
        currentCase.value = await apiService.getClinicalCase(caseId);
      }
      
      // Créer l'attempt (le backend définit expires_at immédiatement)
      currentAttempt.value = await apiService.createAttempt(caseId);
      
      // Initialiser le temps restant avec la durée du cas
      timeRemaining.value = currentCase.value.duration_seconds;
      isExpired.value = false;
      isTimerStarted.value = false; // Pas encore démarré côté UI

      return currentAttempt.value;
    } catch (e: any) {
      error.value = e.message || 'Erreur lors de la création de l\'attempt';
      throw e;
    } finally {
      loading.value = false;
    }
  }

  async function syncTimeRemaining() {
    if (!currentAttempt.value) return;

    try {
      const timeData = await apiService.getTimeRemaining(currentAttempt.value.id);
      timeRemaining.value = timeData.seconds_remaining;
      isExpired.value = timeData.is_expired;
    } catch (e: any) {
      console.error('Erreur lors de la synchronisation du temps:', e);
    }
  }

  function decrementLocalTime() {
    if (timeRemaining.value !== null && timeRemaining.value > 0) {
      timeRemaining.value--;
    } else if (timeRemaining.value === 0) {
      isExpired.value = true;
    }
  }

  function startTimer() {
    if (!currentCase.value || isTimerStarted.value) return;
    
    // Marquer le timer comme démarré pour que ChatHeader lance ses intervals
    isTimerStarted.value = true;
    
    console.log('✅ Timer UI démarré, temps restant:', timeRemaining.value);
  }

  function clearAttempt() {
    currentAttempt.value = null;
    currentCase.value = null;
    timeRemaining.value = null;
    isExpired.value = false;
    isTimerStarted.value = false;
    error.value = null;
  }

  return {
    currentAttempt,
    currentCase,
    timeRemaining,
    isExpired,
    loading,
    error,
    hasActiveAttempt,
    durationSeconds,
    isTimerStarted,
    selectCase,
    createAttempt,
    syncTimeRemaining,
    decrementLocalTime,
    startTimer,
    clearAttempt,
  };
});
