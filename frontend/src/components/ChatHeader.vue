<template>
    <header class="chat-header">
        <div class="case-title">
            <h1>{{ title || 'Chargement…' }}</h1>
            <p class="ai-notice">
                <i class="pi pi-sparkles" aria-hidden="true"></i>
                {{ aiNotice }}
            </p>
        </div>

        <div class="header-actions">
            <!-- Minuteur : lu à la demande (role=timer), annoncé seulement aux paliers -->
            <div class="timer" :class="timerColorClass" role="timer" aria-label="Temps restant">
                <i class="pi pi-clock" aria-hidden="true"></i>
                <span class="timer-display">{{ formattedTime }}</span>
                <span class="sr-only">{{ spokenTime }}</span>
            </div>

            <Button
                label="Terminer"
                severity="danger"
                icon="pi pi-stop"
                @click="handleStop"
                :disabled="isExpired || isFinalizing"
                :loading="isFinalizing"
            />
        </div>

        <p class="sr-only" aria-live="assertive" aria-atomic="true">{{ announcement }}</p>
    </header>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue';
import { useRouter } from 'vue-router';
import Button from 'primevue/button';
import { useToast } from 'primevue/usetoast';
import { apiService } from '../services/api';
import { errorMessage } from '../services/http';
import { EXPIRED_MESSAGE } from '../services/chat';
import type { Interlocutor } from '../types';

const props = withDefaults(defineProps<{
    attemptId: string;
    title?: string;
    interlocutor?: Interlocutor;
}>(), {
    title: '',
    interlocutor: 'patient',
});

const router = useRouter();
const toast = useToast();

// Transparence (AI Act, art. 50) : l'interlocuteur et la correction sont produits par une IA
const aiNotice = computed(() => {
    switch (props.interlocutor) {
        case 'professionnel': return 'Professionnel de santé simulé par une intelligence artificielle';
        case 'aucun': return 'Correction proposée par une intelligence artificielle';
        default: return 'Patient simulé par une intelligence artificielle';
    }
});

/** Heure d'expiration absolue (autorité : le serveur) ; évite les dérives quand l'onglet dort */
const expiresAt = ref<Date | null>(null);
const secondsRemaining = ref<number>(0);
const isExpired = ref(false);
const isFinalizing = ref(false);
const isLoadingData = ref(true);
/** Annonce pour les lecteurs d'écran : seulement à 5 min, 1 min et à la fin */
const announcement = ref('');
const announced = new Set<string>();

let countdownInterval: number | null = null;
let syncInterval: number | null = null;

const formattedTime = computed(() => {
    if (isLoadingData.value || (!expiresAt.value && !isExpired.value)) return '--:--';
    if (isExpired.value) return '00:00';
    const minutes = Math.floor(secondsRemaining.value / 60);
    const seconds = Math.floor(secondsRemaining.value % 60);
    return `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
});

/** Lecture vocale du temps (à la minute près, pour ne pas changer chaque seconde) */
const spokenTime = computed(() => {
    if (isExpired.value) return 'Temps écoulé';
    if (isLoadingData.value || !expiresAt.value) return 'non démarré';
    const minutes = Math.ceil(secondsRemaining.value / 60);
    return minutes <= 1 ? 'moins d’une minute' : `environ ${minutes} minutes`;
});

/** Rouge < 2 min, orange < 5 min, vert sinon */
const timerColorClass = computed(() => {
    if (isExpired.value) return 'timer-expired';
    if (!expiresAt.value) return 'timer-normal';
    if (secondsRemaining.value < 120) return 'timer-critical';
    if (secondsRemaining.value < 300) return 'timer-warning';
    return 'timer-normal';
});

function announce(key: string, text: string) {
    if (announced.has(key)) return;
    announced.add(key);
    announcement.value = text;
}

const THRESHOLDS = [
    { key: '5min', seconds: 300, text: 'Il reste cinq minutes.' },
    { key: '1min', seconds: 60, text: 'Il reste une minute.' },
] as const;

/**
 * Annonce le palier franchi (le dernier si plusieurs, onglet en veille).
 * Au chargement, les paliers déjà dépassés sont notés sans être annoncés.
 */
function announceThresholds(initial = false) {
    for (const { key, seconds, text } of THRESHOLDS) {
        if (secondsRemaining.value > seconds || announced.has(key)) continue;
        if (initial) announced.add(key);
        else announce(key, text);
    }
}

function parseUtc(iso: string): Date {
    // Le serveur renvoie un datetime UTC sans suffixe : on l'ajoute
    return new Date(/[zZ]|[+-]\d\d:?\d\d$/.test(iso) ? iso : `${iso}Z`);
}

async function loadTimer() {
    try {
        isLoadingData.value = true;
        const timeData = await apiService.getTimeRemaining(props.attemptId);
        if (timeData.is_expired) {
            // Station déjà terminée (retour sur la page) : directement au débriefing
            await expire(true);
            return;
        }
        if (timeData.expires_at) {
            expiresAt.value = parseUtc(timeData.expires_at);
            updateSecondsRemaining(true);
        }
    } catch {
        // Minuteur indisponible : la station reste utilisable, le serveur fait foi
    } finally {
        isLoadingData.value = false;
    }
}

/** Appelée chaque seconde : temps restant d'après l'heure d'expiration */
function updateSecondsRemaining(initial = false) {
    if (!expiresAt.value) {
        secondsRemaining.value = 0;
        return;
    }
    const remaining = (expiresAt.value.getTime() - Date.now()) / 1000;
    if (remaining <= 0) {
        void expire();
    } else {
        secondsRemaining.value = remaining;
        announceThresholds(initial);
    }
}

/** Resynchronisation toutes les 30 s et au retour sur l'onglet */
async function syncWithBackend() {
    try {
        const data = await apiService.getTimeRemaining(props.attemptId);
        if (data.is_expired) {
            await expire();
            return;
        }
        if (data.expires_at) {
            const backendExpiresAt = parseUtc(data.expires_at);
            const drift = expiresAt.value
                ? Math.abs(backendExpiresAt.getTime() - expiresAt.value.getTime()) / 1000
                : Infinity;
            if (drift > 2) {
                expiresAt.value = backendExpiresAt;
                updateSecondsRemaining();
            }
        }
    } catch {
        // on continue avec le minuteur local
    }
}

function startTimers() {
    countdownInterval = window.setInterval(() => updateSecondsRemaining(), 1000);
    syncInterval = window.setInterval(syncWithBackend, 30000);
}

function stopTimers() {
    if (countdownInterval) {
        clearInterval(countdownInterval);
        countdownInterval = null;
    }
    if (syncInterval) {
        clearInterval(syncInterval);
        syncInterval = null;
    }
}

function handleVisibilityChange() {
    if (document.visibilityState === 'visible' && !isExpired.value) {
        void syncWithBackend();
    }
}

async function finalizeAttempt(): Promise<boolean> {
    if (isFinalizing.value) return false;
    try {
        isFinalizing.value = true;
        await apiService.finalizeAttempt(props.attemptId);
        await router.push({ name: 'debrief', params: { attemptId: props.attemptId } });
        return true;
    } catch (error) {
        toast.add({
            severity: 'error',
            summary: 'Station non terminée',
            detail: errorMessage(error, 'La station n’a pas pu être terminée. Réessayez.'),
            life: 8000,
        });
        return false;
    } finally {
        isFinalizing.value = false;
    }
}

/**
 * Temps écoulé (minuteur local, serveur, ou réponse 410 du chat) :
 * annonce, puis passage au débriefing.
 */
async function expire(quiet = false) {
    if (isExpired.value) return;
    isExpired.value = true;
    secondsRemaining.value = 0;
    stopTimers();
    if (!quiet) {
        announce('end', EXPIRED_MESSAGE);
        toast.add({ severity: 'info', summary: EXPIRED_MESSAGE, detail: 'Passage au débriefing.', life: 6000 });
    }
    await finalizeAttempt();
}

async function handleStop() {
    const confirmed = window.confirm('Voulez-vous vraiment terminer cette station ?');
    if (!confirmed) return;
    stopTimers();
    const done = await finalizeAttempt();
    if (!done && !isExpired.value && expiresAt.value) startTimers();
}

defineExpose({ expire });

onMounted(async () => {
    await loadTimer();
    if (!isExpired.value && expiresAt.value) {
        startTimers();
    }
    document.addEventListener('visibilitychange', handleVisibilityChange);
});

onUnmounted(() => {
    stopTimers();
    document.removeEventListener('visibilitychange', handleVisibilityChange);
});
</script>

<style scoped>
.chat-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    flex-wrap: wrap;
    padding: 1rem 1.5rem;
    background-color: #ffffff;
    border-bottom: 2px solid #e9ecef;
    box-shadow: 0 2px 4px rgba(0, 0, 0, 0.05);
    gap: 0.75rem 1rem;
}

.case-title {
    flex: 1;
    min-width: min(16rem, 100%);
}

.case-title h1 {
    margin: 0;
    font-size: 1.25rem;
    font-weight: 600;
    color: #212529;
    overflow-wrap: anywhere;
}

.case-title .ai-notice {
    margin: 0.2rem 0 0;
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
    transition: background-color 0.3s ease, color 0.3s ease;
}

.timer i {
    font-size: 1.2rem;
}

/* Couleurs selon le temps restant (contraste ≥ 4,5:1) */
.timer-normal {
    background-color: #d4edda;
    color: #155724;
}

.timer-warning {
    background-color: #fff3cd;
    color: #6b4f00;
}

.timer-critical {
    background-color: #f8d7da;
    color: #721c24;
    animation: pulse 1s infinite;
}

.timer-expired {
    background-color: #343a40;
    color: #ffffff;
}

@keyframes pulse {
    0%, 100% {
        opacity: 1;
    }
    50% {
        opacity: 0.7;
    }
}

@media (prefers-reduced-motion: reduce) {
    .timer-critical {
        animation: none;
    }
    .timer {
        transition: none;
    }
}

.timer-display {
    font-variant-numeric: tabular-nums;
    min-width: 4ch;
}

@media (max-width: 768px) {
    .chat-header {
        padding: 0.75rem 1rem;
    }

    .case-title h1 {
        font-size: 1.05rem;
    }

    .timer {
        font-size: 1rem;
        padding: 0.4rem 0.8rem;
    }
}
</style>
