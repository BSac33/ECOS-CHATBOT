<template>
    <div style="display:flex; min-height:0; flex-direction: column; height:100%">
        <!-- Header fixe avec timer et bouton Stop -->
        <ChatHeader :attempt-id="attemptId" />

        <!-- Container principal avec messages et textbox -->
        <div style="display:flex; min-height:0; gap:1rem; flex-direction: column; padding:1rem; flex: 1;">
            <!-- Container des messages avec scroll automatique -->
            <div 
                id="message-container" 
                ref="messageContainer"
                style="display: flex; flex-direction: column; min-height: 0; flex:1; overflow-y: auto; padding: .5rem;"
            >
                <!-- État de chargement initial -->
                <div v-if="isLoading" style="text-align: center; padding: 2rem; color: #6c757d;">
                    <p>Chargement de la conversation...</p>
                </div>

                <!-- Liste des messages -->
                <Message 
                    v-for="message in messages" 
                    :key="message.id" 
                    :message="message" 
                />

                <!-- Indicateur de frappe (optionnel) -->
                <div v-if="isPatientTyping" class="typing-indicator">
                    <span></span>
                    <span></span>
                    <span></span>
                </div>
            </div>

            <!-- Le patient parle : possibilité de lui couper la parole -->
            <div v-if="isPatientSpeaking" class="speaking-bar">
                <i class="pi pi-volume-up"></i>
                <span>Le patient parle…</span>
                <Button label="Couper" size="small" text severity="secondary" @click="voice.interrupt()" />
            </div>

            <!-- Saisie : clavier ou voix -->
            <div class="input-row">
                <Textbox 
                    style="padding:.5rem; flex: 1;" 
                    @send-message="handleSendMessage"
                    :disabled="isSendingMessage || voiceState !== 'idle'"
                />
                <Button
                    class="mic-button"
                    :class="{ recording: voiceState === 'recording' }"
                    :icon="micIcon"
                    :severity="voiceState === 'recording' ? 'danger' : 'secondary'"
                    :loading="voiceState === 'connecting' || voiceState === 'transcribing'"
                    :disabled="isSendingMessage"
                    :aria-label="micLabel"
                    :title="micLabel"
                    @click="toggleTalking"
                />
            </div>
        </div>
    </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount, nextTick } from 'vue';
import { useRoute } from 'vue-router';
import Button from 'primevue/button';
import ChatHeader from './components/ChatHeader.vue';
import Message from './components/Message.vue';
import Textbox from './components/Textbox.vue';
import { readSSE } from './services/sse';
import { VoiceClient, type VoiceEvent } from './services/voice';

// ============= INTERFACES =============

/**
 * Interface correspondant au format de message du backend
 * Compatible avec le composant Message.vue
 */
interface ChatMessage {
    id: string;
    role: 'student' | 'patient' | 'system' | 'examiner';
    content: string;
    created_at: string;
    attachment_id?: string | null;
    attachment_mime_type?: string | null;
    // "text" ou "voice"
    modality?: string;
    // Message étudiant refusé par les garde-fous (non transmis au patient)
    blocked?: boolean;
    // Transcription vocale en cours
    pending?: boolean;
}

/**
 * Information transmise par l'examinateur (résultats d'examen, document affiché)
 */
interface ExaminerNote {
    kind: 'exam_findings' | 'document';
    title: string;
    content: string;
    attachment_id?: string | null;
    file_url?: string | null;
    mime_type?: string | null;
}

/**
 * Fin d'un tour (événement "done") : réponse complète telle qu'enregistrée
 */
interface ChatResponse {
    patient_reply: string;
    attachments?: string[];
    blocked?: boolean;
    examiner_notes?: ExaminerNote[];
}

/**
 * Convertit une note de l'examinateur au même format que les messages
 * "examiner" renvoyés par GET /messages (rechargement de la page)
 */
function examinerNoteToMessage(note: ExaminerNote): ChatMessage {
    const content = note.kind === 'document'
        ? `Document affiché – ${note.title}`
        : `Examen clinique – ${note.title} : ${note.content}`;
    return {
        id: crypto.randomUUID(),
        role: 'examiner',
        content,
        created_at: new Date().toISOString(),
        attachment_id: note.attachment_id ?? null,
        attachment_mime_type: note.mime_type ?? null,
    };
}

// ============= STATE RÉACTIF =============

const route = useRoute();
const attemptId = route.params.attemptId as string;

/**
 * Référence au container DOM pour le scroll automatique
 */
const messageContainer = ref<HTMLElement | null>(null);

/**
 * Array réactive contenant tous les messages de la conversation
 * Alimentée par le fetch initial puis par les mises à jour optimistes
 */
const messages = ref<ChatMessage[]>([]);

/**
 * Indicateurs d'état pour l'UI
 */
const isLoading = ref(true);
const isSendingMessage = ref(false);
const isPatientTyping = ref(false);

// ============= FONCTIONS UTILITAIRES =============

/**
 * Scroll automatique vers le bas du container de messages
 * Utilise nextTick pour attendre que le DOM soit mis à jour
 */
async function scrollToBottom() {
    await nextTick();
    if (messageContainer.value) {
        messageContainer.value.scrollTop = messageContainer.value.scrollHeight;
    }
}

/**
 * Ajoute un message et renvoie son proxy réactif (pour le modifier ensuite)
 */
function pushMessage(message: ChatMessage): ChatMessage {
    messages.value.push(message);
    return messages.value[messages.value.length - 1]!;
}

function removeMessages(ids: string[]) {
    messages.value = messages.value.filter(m => !ids.includes(m.id));
}

function pushNotice(content: string) {
    pushMessage({ id: crypto.randomUUID(), role: 'system', content, created_at: new Date().toISOString() });
    scrollToBottom();
}

/**
 * Charge l'historique complet des messages depuis le backend
 * Appelée au montage du composant
 */
async function loadMessages() {
    try {
        isLoading.value = true;
        
        // Appel API : GET /chat/attempts/{attemptId}/messages
        const response = await fetch(`/chat/attempts/${attemptId}/messages`, {
            credentials: 'include'
        });
        
        if (!response.ok) {
            throw new Error('Erreur lors du chargement des messages');
        }
        
        const data: ChatMessage[] = await response.json();
        
        // Stocker les messages dans l'array réactive
        messages.value = data;
        
        // Scroll automatique après le chargement
        await scrollToBottom();
        
    } catch (error) {
        console.error('Erreur lors du chargement des messages:', error);
        // TODO: Afficher un message d'erreur à l'utilisateur
    } finally {
        isLoading.value = false;
    }
}

// ============= AFFICHAGE D'UN TOUR (commun écrit / vocal) =============

interface Turn {
    delta(text: string): void;
    note(note: ExaminerNote): void;
    done(final: ChatResponse): void;
    /** Échec : rien n'a été enregistré, on retire la réponse partielle */
    fail(): void;
}

/**
 * Affichage progressif de la réplique du patient en réponse à un message étudiant.
 * La bulle du patient est créée au premier morceau de texte ; les notes de
 * l'examinateur arrivées avant sont affichées juste après elle.
 */
function startTurn(studentMessageId: string, modality: 'text' | 'voice'): Turn {
    let patientMessage: ChatMessage | null = null;
    let pendingNotes: ChatMessage[] = [];
    const addedIds: string[] = [];

    const add = (message: ChatMessage) => {
        addedIds.push(message.id);
        return pushMessage(message);
    };
    const ensurePatientBubble = (): ChatMessage => {
        if (!patientMessage) {
            isPatientTyping.value = false;
            patientMessage = add({
                id: crypto.randomUUID(),
                role: 'patient',
                content: '',
                created_at: new Date().toISOString(),
                modality,
            });
            pendingNotes.forEach(add);
            pendingNotes = [];
        }
        return patientMessage;
    };

    isPatientTyping.value = true;
    return {
        delta(text) {
            ensurePatientBubble().content += text;
            scrollToBottom();
        },
        note(note) {
            const message = examinerNoteToMessage(note);
            if (patientMessage) add(message);
            else pendingNotes.push(message);
            scrollToBottom();
        },
        done(final) {
            isPatientTyping.value = false;
            if (final.blocked) {
                // Le message n'entre pas dans le transcript : on le marque comme non transmis
                // et on affiche l'avertissement comme message système (hors personnage).
                const sent = messages.value.find(m => m.id === studentMessageId);
                if (sent) sent.blocked = true;
                add({ id: crypto.randomUUID(), role: 'system', content: final.patient_reply, created_at: new Date().toISOString() });
            } else {
                // Texte de référence tel qu'enregistré
                ensurePatientBubble().content = final.patient_reply;
            }
            scrollToBottom();
        },
        fail() {
            isPatientTyping.value = false;
            removeMessages(addedIds);
        },
    };
}

// ============= MODE ÉCRIT (SSE) =============

/**
 * Gère l'envoi d'un nouveau message depuis le composant Textbox
 * La réplique du patient arrive en flux (SSE) et s'affiche au fil de l'eau
 * 
 * @param messageContent - Le contenu du message saisi par l'étudiant
 */
async function handleSendMessage(messageContent: string) {
    if (!messageContent.trim() || isSendingMessage.value) {
        return;
    }
    
    let turn: Turn | null = null;
    try {
        isSendingMessage.value = true;
        
        // ===== MISE À JOUR OPTIMISTE =====
        const studentMessage = pushMessage({
            id: crypto.randomUUID(), // ID temporaire
            role: 'student',
            content: messageContent,
            created_at: new Date().toISOString(),
            modality: 'text',
        });
        await scrollToBottom();
        
        isPatientTyping.value = true;
        
        // POST /chat/attempts/{attemptId}/chat/stream
        const response = await fetch(`/chat/attempts/${attemptId}/chat/stream`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Accept': 'text/event-stream'
            },
            credentials: 'include',
            body: JSON.stringify({ message: messageContent })
        });
        
        // Les erreurs de validation (temps écoulé, tentative terminée...) restent des erreurs HTTP
        if (!response.ok) {
            const error = await response.json().catch(() => ({ detail: 'Erreur réseau' }));
            throw new Error(error.detail || 'Erreur lors de l\'envoi du message');
        }
        
        turn = startTurn(studentMessage.id, 'text');
        const current = turn;
        let finished = false;
        let streamError: string | null = null;
        
        await readSSE(response, ({ event, data }) => {
            switch (event) {
                case 'delta':
                    current.delta((data as { text: string }).text);
                    break;
                case 'examiner_note':
                    current.note(data as ExaminerNote);
                    break;
                case 'done':
                    current.done(data as ChatResponse);
                    finished = true;
                    break;
                case 'error':
                    streamError = (data as { message?: string }).message ?? 'Erreur du patient simulé';
                    break;
            }
        });
        
        // Échec ou flux coupé : rien n'a été enregistré, on retire la réponse partielle
        if (!finished) {
            current.fail();
            throw new Error(streamError ?? 'La connexion a été interrompue avant la fin de la réponse');
        }
        
    } catch (error) {
        console.error('Erreur lors de l\'envoi du message:', error);
        alert(`Erreur: ${error instanceof Error ? error.message : 'Erreur inconnue'}`);
        
    } finally {
        isSendingMessage.value = false;
        isPatientTyping.value = false;
    }
}

// ============= MODE VOCAL (appuyer pour parler) =============

const voice = new VoiceClient(attemptId);
const voiceState = ref<'idle' | 'connecting' | 'recording' | 'transcribing'>('idle');
const isPatientSpeaking = ref(false);
let speakingStudent: ChatMessage | null = null;   // bulle étudiant en cours de transcription
const voiceTurns: Turn[] = [];                     // tours en attente de "done", dans l'ordre
let voiceUnavailableShown = false;

const micIcon = computed(() => voiceState.value === 'recording' ? 'pi pi-stop-circle' : 'pi pi-microphone');
const micLabel = computed(() => voiceState.value === 'recording'
    ? 'Terminer et envoyer'
    : 'Parler au patient (cliquer pour commencer, recliquer pour envoyer)');

voice.onSpeakingChange = (speaking) => { isPatientSpeaking.value = speaking; };
voice.onEvent = handleVoiceEvent;

async function toggleTalking() {
    if (voiceState.value === 'recording') {
        voice.stopTalking();
        voiceState.value = 'transcribing';
        return;
    }
    if (voiceState.value !== 'idle') return;
    try {
        voiceState.value = 'connecting';
        await voice.startTalking();
        speakingStudent = pushMessage({
            id: crypto.randomUUID(),
            role: 'student',
            content: '',
            created_at: new Date().toISOString(),
            modality: 'voice',
            pending: true,
        });
        voiceState.value = 'recording';
        scrollToBottom();
    } catch (error) {
        voiceState.value = 'idle';
        const reason = error instanceof Error ? error.message : 'erreur inconnue';
        alert(`Mode vocal indisponible : ${reason}`);
    }
}

function handleVoiceEvent(event: VoiceEvent) {
    switch (event.type) {
        case 'transcript_partial':
            if (speakingStudent) speakingStudent.content = event.text as string;
            scrollToBottom();
            break;
        case 'transcript_final': {
            voiceState.value = 'idle';
            const student = speakingStudent;
            speakingStudent = null;
            if (!student) break;
            const text = (event.text as string) || '';
            if (!text) {
                removeMessages([student.id]);
                pushNotice("Je n'ai rien entendu. Vérifiez votre micro et réessayez.");
                break;
            }
            student.content = text;
            student.pending = false;
            voiceTurns.push(startTurn(student.id, 'voice'));
            break;
        }
        case 'delta':
            voiceTurns[0]?.delta(event.text as string);
            break;
        case 'examiner_note':
            voiceTurns[0]?.note(event as unknown as ExaminerNote);
            break;
        case 'done':
            voiceTurns.shift()?.done(event as unknown as ChatResponse);
            break;
        case 'voice_unavailable':
            if (!voiceUnavailableShown) pushNotice(event.message as string);
            voiceUnavailableShown = true;
            break;
        case 'error':
            if (speakingStudent) {
                // La transcription a échoué : rien n'a été envoyé
                removeMessages([speakingStudent.id]);
                speakingStudent = null;
            } else {
                voiceTurns.shift()?.fail();
            }
            voiceState.value = 'idle';
            isPatientTyping.value = false;
            pushNotice((event.message as string) || 'Erreur du mode vocal');
            break;
        case 'closed':
            voiceState.value = 'idle';
            isPatientSpeaking.value = false;
            if (speakingStudent) {
                removeMessages([speakingStudent.id]);
                speakingStudent = null;
            }
            voiceTurns.splice(0).forEach(turn => turn.fail());
            break;
    }
}

// ============= LIFECYCLE HOOKS =============

/**
 * Au montage du composant :
 * 1. Charger l'historique des messages
 * 2. Initialiser le scroll en bas de page
 */
onMounted(async () => {
    await loadMessages();
});

onBeforeUnmount(() => {
    voice.close();
});

</script>

<style scoped>
/* Animation de l'indicateur de frappe (typing indicator) */
.typing-indicator {
    display: flex;
    align-items: center;
    gap: 0.25rem;
    padding: 0.75rem 1rem;
    margin-left: 0.5rem;
    max-width: 70%;
}

.typing-indicator span {
    width: 8px;
    height: 8px;
    background-color: #6c757d;
    border-radius: 50%;
    animation: typing 1.4s infinite;
}

.typing-indicator span:nth-child(2) {
    animation-delay: 0.2s;
}

.typing-indicator span:nth-child(3) {
    animation-delay: 0.4s;
}

@keyframes typing {
    0%, 60%, 100% {
        opacity: 0.3;
        transform: translateY(0);
    }
    30% {
        opacity: 1;
        transform: translateY(-10px);
    }
}

/* Saisie : zone de texte + bouton micro */
.input-row {
    display: flex;
    align-items: center;
    gap: 0.5rem;
}

.mic-button {
    width: 3.25rem;
    height: 3.25rem;
    flex-shrink: 0;
}

.mic-button.recording {
    animation: pulse 1.2s infinite;
}

@keyframes pulse {
    0%, 100% { box-shadow: 0 0 0 0 rgba(220, 53, 69, 0.45); }
    50% { box-shadow: 0 0 0 8px rgba(220, 53, 69, 0); }
}

.speaking-bar {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0 0.75rem;
    color: #495057;
    font-size: 0.9rem;
}

/* Style du container de messages */
#message-container {
    scroll-behavior: smooth;
}

#message-container::-webkit-scrollbar {
    width: 8px;
}

#message-container::-webkit-scrollbar-track {
    background: #f1f1f1;
    border-radius: 10px;
}

#message-container::-webkit-scrollbar-thumb {
    background: #888;
    border-radius: 10px;
}

#message-container::-webkit-scrollbar-thumb:hover {
    background: #555;
}
</style>