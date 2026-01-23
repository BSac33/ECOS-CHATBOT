<template>
    <div class="chat-header">
        <!-- Titre du cas (tronqué si trop long) -->
        <div class="case-title">
            <h2>{{ caseTitle || 'Chargement...' }}</h2>
        </div>

        <!-- Partie droite : Timer + Bouton Stop -->
        <div class="header-actions">
            <!-- Timer avec code couleur selon le temps restant -->
            <div class="timer" :class="timerColorClass">
                <i class="pi pi-clock"></i>
                <span class="timer-display">{{ formattedTime }}</span>
            </div>

            <!-- Bouton Stop pour finaliser l'attempt -->
            <Button 
                label="Terminer" 
                severity="danger"
                icon="pi pi-stop"
                @click="handleStop"
                :disabled="isExpired || isFinalizing"
                :loading="isFinalizing"
            />
        </div>
    </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue';
import { useRouter } from 'vue-router';
import Button from 'primevue/button';

// ============= PROPS =============

interface ChatHeaderProps {
    attemptId: string;
}

const props = defineProps<ChatHeaderProps>();

// ============= STATE RÉACTIF =============

const router = useRouter();

/**
 * Titre du cas clinique
 */
const caseTitle = ref<string>('');

/**
 * Timestamp absolu d'expiration (autorité)
 * Utiliser un timestamp absolu évite les dérives dues à la suspension du JS
 */
const expiresAt = ref<Date | null>(null);

/**
 * Secondes restantes calculées en temps réel
 */
const secondsRemaining = ref<number>(0);

/**
 * Indicateurs d'état
 */
const isExpired = ref(false);
const isFinalizing = ref(false);
const isLoadingData = ref(true);

/**
 * Intervalles pour le décompte et la synchronisation
 */
let countdownInterval: number | null = null;
let syncInterval: number | null = null;

// ============= COMPUTED =============

/**
 * Formate le temps restant en MM:SS
 */
const formattedTime = computed(() => {
    if (isLoadingData.value) return '--:--';
    if (isExpired.value) return '00:00';
    
    const minutes = Math.floor(secondsRemaining.value / 60);
    const seconds = Math.floor(secondsRemaining.value % 60);
    
    return `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
});

/**
 * Classe CSS conditionnelle selon le temps restant
 * Rouge < 2min, Orange < 5min, Vert sinon
 */
const timerColorClass = computed(() => {
    if (isExpired.value || secondsRemaining.value === 0) return 'timer-expired';
    if (secondsRemaining.value < 120) return 'timer-critical'; // < 2min
    if (secondsRemaining.value < 300) return 'timer-warning'; // < 5min
    return 'timer-normal';
});

// ============= FONCTIONS =============

/**
 * Charge les informations initiales (titre + timer)
 * Récupère expires_at depuis le backend
 */
async function loadInitialData() {
    try {
        isLoadingData.value = true;
        
        // Fetch en parallèle : titre du cas + temps restant
        const [timeResponse, caseResponse] = await Promise.all([
            fetch(`/chat/attempts/${props.attemptId}/time-remaining`, {
                credentials: 'include'
            }),
            // Fetch du cas pour récupérer le titre (via les messages ou une route dédiée)
            fetch(`/chat/attempts/${props.attemptId}/messages`, {
                credentials: 'include'
            })
        ]);

        if (!timeResponse.ok) {
            throw new Error('Erreur lors du chargement du timer');
        }

        const timeData = await timeResponse.json();
        
        console.log('📊 Données timer reçues:', timeData);
        
        // Vérifier si déjà expiré
        if (timeData.is_expired) {
            console.warn('⚠️ Attempt déjà expiré, finalisation...');
            isExpired.value = true;
            secondsRemaining.value = 0;
            await finalizeAttempt(); // Auto-finaliser
            return;
        }

        // Stocker le timestamp absolu d'expiration
        if (timeData.expires_at) {
            // IMPORTANT : Le backend renvoie un datetime UTC sans le suffixe 'Z'
            // On doit l'ajouter pour que JavaScript l'interprète correctement en UTC
            const expiresAtISO = timeData.expires_at.endsWith('Z') 
                ? timeData.expires_at 
                : timeData.expires_at + 'Z';
            
            expiresAt.value = new Date(expiresAtISO);
            console.log('✅ Timer initialisé:', {
                raw: timeData.expires_at,
                parsed: expiresAt.value.toISOString()
            });
            updateSecondsRemaining();
        } else {
            // Si pas d'expires_at, c'est que le timer n'a pas démarré
            // Ne pas bloquer l'interface, afficher "--:--"
            console.log('ℹ️ Timer pas encore démarré (expires_at manquant)');
        }

        // Extraire le titre du cas depuis le premier message système
        if (caseResponse.ok) {
            const messages = await caseResponse.json();
            const systemMessage = messages.find((m: any) => m.role === 'system');
            if (systemMessage) {
                // Le titre est dans les instructions, on prend les 50 premiers caractères
                caseTitle.value = extractCaseTitle(systemMessage.content);
            }
        }

    } catch (error) {
        console.error('Erreur lors du chargement des données:', error);
        caseTitle.value = 'Cas clinique';
    } finally {
        isLoadingData.value = false;
    }
}

/**
 * Extrait un titre court depuis le contenu du message système
 */
function extractCaseTitle(content: string): string {
    // Prendre les 60 premiers caractères, couper au dernier espace
    const maxLength = 60;
    if (content.length <= maxLength) return content;
    
    const truncated = content.substring(0, maxLength);
    const lastSpace = truncated.lastIndexOf(' ');
    
    return lastSpace > 0 ? truncated.substring(0, lastSpace) + '...' : truncated + '...';
}

/**
 * Met à jour le temps restant en calculant la différence avec expires_at
 * Cette fonction est appelée chaque seconde par le timer local
 */
function updateSecondsRemaining() {
    if (!expiresAt.value) {
        secondsRemaining.value = 0;
        return;
    }

    // Utiliser UTC pour la comparaison (le backend utilise datetime.utcnow())
    const nowUTC = Date.now(); // Timestamp en millisecondes (toujours UTC)
    const expiresAtUTC = expiresAt.value.getTime();
    const remaining = (expiresAtUTC - nowUTC) / 1000;
    
    console.log('⏱️ Calcul temps restant:', {
        nowUTC: new Date(nowUTC).toISOString(),
        expiresAtUTC: expiresAt.value.toISOString(),
        remaining: remaining.toFixed(1) + 's'
    });
    
    if (remaining <= 0) {
        secondsRemaining.value = 0;
        isExpired.value = true;
        stopTimers();
        finalizeAttempt(); // Auto-finaliser quand le temps expire
    } else {
        secondsRemaining.value = remaining;
    }
}

/**
 * Synchronise le timer avec le backend
 * Appelée toutes les 30 secondes et lors du retour de focus
 */
async function syncWithBackend() {
    try {
        const response = await fetch(`/chat/attempts/${props.attemptId}/time-remaining`, {
            credentials: 'include'
        });

        if (!response.ok) return;

        const data = await response.json();

        // Vérifier si expiré côté backend
        if (data.is_expired) {
            isExpired.value = true;
            secondsRemaining.value = 0;
            stopTimers();
            await finalizeAttempt();
            return;
        }

        // Recalculer expires_at si fourni
        if (data.expires_at) {
            // IMPORTANT : Ajouter 'Z' pour forcer l'interprétation UTC
            const expiresAtISO = data.expires_at.endsWith('Z') 
                ? data.expires_at 
                : data.expires_at + 'Z';
            
            const backendExpiresAt = new Date(expiresAtISO);
            const localExpiresAt = expiresAt.value;

            if (localExpiresAt) {
                // Calculer l'écart entre le backend et le local
                const drift = Math.abs(backendExpiresAt.getTime() - localExpiresAt.getTime()) / 1000;

                // Si l'écart dépasse 2 secondes, corriger
                if (drift > 2) {
                    console.log(`🔄 Correction de dérive du timer : ${drift.toFixed(1)}s`);
                    expiresAt.value = backendExpiresAt;
                    updateSecondsRemaining();
                }
            }
        }

    } catch (error) {
        console.error('Erreur lors de la synchronisation du timer:', error);
        // En cas d'erreur, continuer avec le timer local
    }
}

/**
 * Démarrer les timers (décompte + synchronisation)
 */
function startTimers() {
    // Timer local : décompte chaque seconde
    countdownInterval = window.setInterval(() => {
        updateSecondsRemaining();
    }, 1000);

    // Synchronisation avec le backend toutes les 30 secondes
    syncInterval = window.setInterval(() => {
        syncWithBackend();
    }, 30000);
}

/**
 * Arrêter tous les timers
 */
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

/**
 * Gestion du retour de focus (tab redevient active)
 * Re-synchronise immédiatement pour corriger toute dérive
 */
function handleVisibilityChange() {
    if (document.visibilityState === 'visible' && !isExpired.value) {
        console.log('🔄 Tab redevenue visible, re-synchronisation...');
        syncWithBackend();
    }
}

/**
 * Finalise l'attempt (appel backend)
 */
async function finalizeAttempt() {
    if (isFinalizing.value) return;

    try {
        isFinalizing.value = true;

        const response = await fetch(`/chat/attempts/${props.attemptId}/finalize`, {
            method: 'POST',
            credentials: 'include'
        });

        if (!response.ok) {
            throw new Error('Erreur lors de la finalisation');
        }

        console.log('✅ Attempt finalisée avec succès');
        
        // Rediriger vers l'évaluation
        router.push(`/evaluation/${props.attemptId}`);

    } catch (error) {
        console.error('Erreur lors de la finalisation:', error);
        alert('Erreur lors de la finalisation de la tentative');
    } finally {
        isFinalizing.value = false;
    }
}

/**
 * Gère le clic sur le bouton Stop
 */
async function handleStop() {
    const confirmed = confirm('Êtes-vous sûr de vouloir terminer cette tentative ?');
    if (!confirmed) return;

    stopTimers();
    await finalizeAttempt();
}

// ============= LIFECYCLE HOOKS =============

onMounted(async () => {
    // 1. Charger les données initiales
    await loadInitialData();

    // 2. Démarrer les timers si pas expiré
    if (!isExpired.value && expiresAt.value) {
        startTimers();
    }

    // 3. Écouter les changements de visibilité (tab inactive/active)
    document.addEventListener('visibilitychange', handleVisibilityChange);
});

onUnmounted(() => {
    // Nettoyer les timers et listeners
    stopTimers();
    document.removeEventListener('visibilitychange', handleVisibilityChange);
});

</script>

<style scoped>
.chat-header {
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
    min-width: 0; /* Permet le text-overflow */
}

.case-title h2 {
    margin: 0;
    font-size: 1.25rem;
    font-weight: 600;
    color: #212529;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
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

.timer i {
    font-size: 1.2rem;
}

/* Couleurs selon le temps restant */
.timer-normal {
    background-color: #d4edda;
    color: #155724;
}

.timer-warning {
    background-color: #fff3cd;
    color: #856404;
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

.timer-display {
    font-variant-numeric: tabular-nums;
    min-width: 4ch;
}

/* Responsive : réduire le padding sur petits écrans */
@media (max-width: 768px) {
    .chat-header {
        padding: 0.75rem 1rem;
        flex-wrap: wrap;
    }

    .case-title h2 {
        font-size: 1rem;
    }

    .timer {
        font-size: 1rem;
        padding: 0.4rem 0.8rem;
    }
}
</style>
