<template>
    <div class="exam-header">
        <div class="case-title">
            <h2>{{ caseTitle || 'Chargement...' }}</h2>
            <span v-if="stationLabel" class="station-label">{{ stationLabel }}</span>
        </div>

        <div class="header-actions">
            <div class="timer" :class="timerColorClass">
                <i class="pi pi-clock"></i>
                <span class="timer-display">{{ formattedTime }}</span>
            </div>
        </div>
    </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue';

interface ExamHeaderProps {
    attemptId: string;
}

const props = defineProps<ExamHeaderProps>();

// Émis quand le temps expire : le parent doit gérer la finalisation
const emit = defineEmits<{
    expired: [];
}>();

const caseTitle = ref<string>('');
const stationLabel = ref<string>('');
const expiresAt = ref<Date | null>(null);
const secondsRemaining = ref<number>(0);
const isExpired = ref(false);
const isLoadingData = ref(true);

let countdownInterval: number | null = null;
let syncInterval: number | null = null;

const stationTypeLabels: Record<string, string> = {
    exam_analysis: 'Analyse d\'examens',
    procedure: 'Geste technique',
    patient_interview: 'Interrogatoire patient',
    diagnosis_announcement: 'Annonce diagnostique',
    mixed: 'Station mixte',
};

const formattedTime = computed(() => {
    if (isLoadingData.value) return '--:--';
    if (isExpired.value) return '00:00';
    const minutes = Math.floor(secondsRemaining.value / 60);
    const seconds = Math.floor(secondsRemaining.value % 60);
    return `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
});

const timerColorClass = computed(() => {
    if (isExpired.value || secondsRemaining.value === 0) return 'timer-expired';
    if (secondsRemaining.value < 120) return 'timer-critical';
    if (secondsRemaining.value < 300) return 'timer-warning';
    return 'timer-normal';
});

async function loadInitialData() {
    try {
        isLoadingData.value = true;

        const [caseInfoResponse, timeResponse] = await Promise.all([
            fetch(`/chat/attempts/${props.attemptId}/case-info`, { credentials: 'include' }),
            fetch(`/chat/attempts/${props.attemptId}/time-remaining`, { credentials: 'include' })
        ]);

        if (caseInfoResponse.ok) {
            const caseInfo = await caseInfoResponse.json();
            caseTitle.value = caseInfo.title;
            stationLabel.value = stationTypeLabels[caseInfo.station_type] || caseInfo.station_type;
        }

        if (!timeResponse.ok) throw new Error('Erreur timer');

        const timeData = await timeResponse.json();

        if (timeData.is_expired) {
            isExpired.value = true;
            secondsRemaining.value = 0;
            emit('expired');
            return;
        }

        if (timeData.expires_at) {
            const iso = timeData.expires_at.endsWith('Z') ? timeData.expires_at : timeData.expires_at + 'Z';
            expiresAt.value = new Date(iso);
            updateSecondsRemaining();
        }
    } catch (error) {
        console.error('Erreur chargement header exam:', error);
        caseTitle.value = 'Cas clinique';
    } finally {
        isLoadingData.value = false;
    }
}

function updateSecondsRemaining() {
    if (!expiresAt.value) { secondsRemaining.value = 0; return; }
    const remaining = (expiresAt.value.getTime() - Date.now()) / 1000;
    if (remaining <= 0) {
        secondsRemaining.value = 0;
        isExpired.value = true;
        stopTimers();
        emit('expired');
    } else {
        secondsRemaining.value = remaining;
    }
}

async function syncWithBackend() {
    try {
        const response = await fetch(`/chat/attempts/${props.attemptId}/time-remaining`, { credentials: 'include' });
        if (!response.ok) return;
        const data = await response.json();
        if (data.is_expired) {
            isExpired.value = true;
            secondsRemaining.value = 0;
            stopTimers();
            emit('expired');
            return;
        }
        if (data.expires_at) {
            const iso = data.expires_at.endsWith('Z') ? data.expires_at : data.expires_at + 'Z';
            const backendExp = new Date(iso);
            if (expiresAt.value) {
                const drift = Math.abs(backendExp.getTime() - expiresAt.value.getTime()) / 1000;
                if (drift > 2) { expiresAt.value = backendExp; updateSecondsRemaining(); }
            }
        }
    } catch (_) { /* continue with local timer */ }
}

function startTimers() {
    countdownInterval = window.setInterval(updateSecondsRemaining, 1000);
    syncInterval = window.setInterval(syncWithBackend, 30000);
}

function stopTimers() {
    if (countdownInterval) { clearInterval(countdownInterval); countdownInterval = null; }
    if (syncInterval) { clearInterval(syncInterval); syncInterval = null; }
}

function handleVisibilityChange() {
    if (document.visibilityState === 'visible' && !isExpired.value) syncWithBackend();
}

onMounted(async () => {
    await loadInitialData();
    if (!isExpired.value && expiresAt.value) startTimers();
    document.addEventListener('visibilitychange', handleVisibilityChange);
});

onUnmounted(() => {
    stopTimers();
    document.removeEventListener('visibilitychange', handleVisibilityChange);
});
</script>

<style scoped>
.exam-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 1rem 1.5rem;
    background-color: #ffffff;
    border-bottom: 2px solid #e9ecef;
    box-shadow: 0 2px 4px rgba(0, 0, 0, 0.05);
    gap: 1rem;
}

.case-title {
    flex: 1;
    min-width: 0;
}

.case-title h2 {
    margin: 0 0 0.25rem 0;
    font-size: 1.25rem;
    font-weight: 600;
    color: #212529;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}

.station-label {
    font-size: 0.8rem;
    color: #6c757d;
    font-weight: 500;
    text-transform: uppercase;
    letter-spacing: 0.05em;
}

.header-actions {
    display: flex;
    align-items: center;
    gap: 1rem;
    flex-shrink: 0;
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

.timer i { font-size: 1.2rem; }

.timer-normal { background-color: #d4edda; color: #155724; }
.timer-warning { background-color: #fff3cd; color: #856404; }
.timer-critical {
    background-color: #f8d7da;
    color: #721c24;
    animation: pulse 1s infinite;
}
.timer-expired { background-color: #343a40; color: #ffffff; }

@keyframes pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.7; }
}

.timer-display {
    font-variant-numeric: tabular-nums;
    min-width: 4ch;
}

@media (max-width: 768px) {
    .exam-header { padding: 0.75rem 1rem; flex-wrap: wrap; }
    .case-title h2 { font-size: 1rem; }
    .timer { font-size: 1rem; padding: 0.4rem 0.8rem; }
}
</style>
