<template>
    <div class="chat-view">
        <!-- En-tête : titre, mention IA, minuteur, bouton Terminer -->
        <ChatHeader
            ref="header"
            :attempt-id="attemptId"
            :title="caseTitle"
            :interlocutor="noInterlocutor ? 'aucun' : interlocutor"
        />

        <div class="chat-body">
            <!-- Consultation orale : pas de texte par défaut, la transcription reste enregistrée -->
            <VoiceConsultation
                v-if="consulting"
                :who="interlocutorLabel"
                :status="consultationStatus"
                :level="micLevel"
                :muted="micMuted"
                :show-transcript="showTranscript"
                :examiner-notes="examinerNotes"
                :notice="consultationNotice"
                @toggle-mute="toggleMute"
                @toggle-transcript="toggleTranscript"
                @interrupt="voice.interrupt()"
                @leave="leaveConsultation"
            />

            <Message v-if="loadError" severity="error" :closable="false" class="load-error">
                <span>{{ loadError }}</span>
                <Button label="Réessayer" icon="pi pi-refresh" size="small" text @click="loadMessages" />
            </Message>

            <!-- Conversation : annoncée au fil de l'eau par les lecteurs d'écran -->
            <div
                v-show="!consulting || showTranscript"
                id="message-container"
                ref="messageContainer"
                class="message-container"
                role="log"
                aria-live="polite"
                aria-label="Conversation"
                :aria-busy="conversationBusy"
                tabindex="0"
            >
                <p v-if="isLoading" class="loading">Chargement de la conversation…</p>

                <ChatBubble
                    v-for="message in messages"
                    :key="message.id"
                    :message="message"
                    :interlocutor="interlocutorLabel"
                    :retry-disabled="isSendingMessage || stationOver"
                    @retry="retryMessage"
                />

                <div v-if="isPatientTyping" class="typing-indicator" aria-hidden="true">
                    <span></span>
                    <span></span>
                    <span></span>
                </div>
            </div>
            <p class="sr-only" role="status">{{ typingStatus }}</p>

            <!-- Le patient parle : possibilité de lui couper la parole -->
            <div v-if="isPatientSpeaking && !consulting" class="speaking-bar">
                <i class="pi pi-volume-up" aria-hidden="true"></i>
                <span>{{ subject }} parle…</span>
                <Button label="Couper" size="small" text severity="secondary" @click="voice.interrupt()" />
            </div>

            <!-- Station sans interlocuteur : rappel de la consigne -->
            <div v-if="noInterlocutor && !consulting" class="silent-hint">
                <i class="pi pi-info-circle" aria-hidden="true"></i>
                Station sans interlocuteur : exposez votre raisonnement à voix haute ou par écrit. Les examinateurs vous écoutent sans intervenir.
            </div>

            <p v-if="stationOver" class="station-over" role="alert">{{ EXPIRED_MESSAGE }}</p>

            <!-- Saisie : clavier ou voix -->
            <div v-if="!consulting" class="input-row">
                <Textbox
                    v-model="draft"
                    class="input-box"
                    :max-length="MAX_MESSAGE_LENGTH"
                    :disabled="isSendingMessage || voiceState !== 'idle' || stationOver"
                    @send-message="handleSendMessage"
                />
                <Button
                    class="mic-button"
                    :class="{ recording: voiceState === 'recording' }"
                    :icon="micIcon"
                    :severity="voiceState === 'recording' ? 'danger' : 'secondary'"
                    :loading="voiceState === 'connecting' || voiceState === 'transcribing'"
                    :disabled="isSendingMessage || stationOver"
                    :aria-label="micLabel"
                    :aria-pressed="voiceState === 'recording'"
                    :title="micLabel"
                    @click="toggleTalking"
                />
                <Button
                    class="mic-button"
                    icon="pi pi-headphones"
                    severity="secondary"
                    outlined
                    :disabled="isSendingMessage || voiceState !== 'idle' || stationOver"
                    aria-label="Consultation orale (mains libres)"
                    title="Consultation orale : parlez librement au patient, sans bouton ni texte"
                    @click="startConsultation"
                />
            </div>
        </div>
    </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount, nextTick } from 'vue';
import Button from 'primevue/button';
import Message from 'primevue/message';
import { useToast } from 'primevue/usetoast';
import ChatHeader from './components/ChatHeader.vue';
import ChatBubble from './components/Message.vue';
import Textbox from './components/Textbox.vue';
import VoiceConsultation, { type ConsultationStatus } from './components/VoiceConsultation.vue';
import { VoiceClient, type VoiceEvent } from './services/voice';
import { apiService } from './services/api';
import { ApiError, errorMessage } from './services/http';
import { EXPIRED_MESSAGE, MAX_MESSAGE_LENGTH, streamChatTurn } from './services/chat';
import type { ChatMessage, ChatResponse, ExaminerNote, Interlocutor } from './types';

const props = defineProps<{ attemptId: string }>();
const attemptId = props.attemptId;
const toast = useToast();

/**
 * Convertit une note de l'examinateur au même format que les messages
 * « examiner » renvoyés par GET /messages (rechargement de la page)
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

// ============= ÉTAT =============

const header = ref<InstanceType<typeof ChatHeader> | null>(null);
const messageContainer = ref<HTMLElement | null>(null);
const messages = ref<ChatMessage[]>([]);
const draft = ref('');

const isLoading = ref(true);
const loadError = ref<string | null>(null);
const isSendingMessage = ref(false);
const isPatientTyping = ref(false);
/** Temps écoulé (réponse 410) : plus d'envoi possible */
const stationOver = ref(false);

const caseTitle = ref('');
const interlocutor = ref<Interlocutor>('patient');
/** Station sans patient ni professionnel simulé : l'étudiant parle seul devant les examinateurs */
const noInterlocutor = computed(() => interlocutor.value === 'aucun');
/** « Patient », « Patiente » ou rôle du professionnel de santé simulé */
const interlocutorLabel = ref('Patient');
const subject = computed(() => {
    if (interlocutorLabel.value === 'Patiente') return 'La patiente';
    if (interlocutorLabel.value === 'Patient') return 'Le patient';
    return interlocutorLabel.value;
});

/** Annulation des envois en cours si l'on quitte la page */
const pageController = new AbortController();

// ============= OUTILS =============

async function scrollToBottom() {
    await nextTick();
    if (messageContainer.value) {
        messageContainer.value.scrollTop = messageContainer.value.scrollHeight;
    }
}

/** Ajoute un message et renvoie son proxy réactif (pour le modifier ensuite) */
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

function showError(summary: string, error: unknown) {
    toast.add({ severity: 'error', summary, detail: errorMessage(error), life: 8000 });
}

async function loadMessages() {
    isLoading.value = true;
    loadError.value = null;
    try {
        messages.value = await apiService.getMessages(attemptId);
        await scrollToBottom();
    } catch (error) {
        loadError.value = `Impossible de charger la conversation. ${errorMessage(error)}`;
    } finally {
        isLoading.value = false;
    }
}

async function loadStationInfo() {
    try {
        const info = await apiService.getAttemptCaseInfo(attemptId);
        caseTitle.value = info.title;
        interlocutor.value = info.interlocutor ?? 'patient';
        interlocutorLabel.value = info.interlocutor_label || 'Patient';
    } catch {
        // information facultative : comportement par défaut (avec patient)
        caseTitle.value = 'Station';
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

    isPatientTyping.value = !noInterlocutor.value;
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
            if (final.silent) {
                // Personne ne répond : seule la parole de l'étudiant est enregistrée
                pendingNotes.forEach(add);
                pendingNotes = [];
            } else if (final.blocked) {
                // Le message n'entre pas dans le transcript : marqué comme non transmis,
                // avertissement affiché comme message système (hors personnage)
                const sent = messages.value.find(m => m.id === studentMessageId);
                if (sent) sent.blocked = true;
                add({ id: crypto.randomUUID(), role: 'system', content: final.patient_reply, created_at: new Date().toISOString() });
            } else {
                // Texte de référence tel qu'enregistré
                const bubble = ensurePatientBubble();
                bubble.content = final.patient_reply;
                bubble.server_id = final.patient_message_id ?? null;
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

const isStreaming = ref(false);

async function sendText(content: string) {
    if (!content.trim() || isSendingMessage.value || stationOver.value) return;
    isSendingMessage.value = true;
    // Le texte remis dans la saisie est renvoyé : l'ancienne bulle « Non envoyé » disparaît
    removeMessages(messages.value.filter(m => m.failed && m.content === content).map(m => m.id));

    // Mise à jour optimiste
    const studentMessage = pushMessage({
        id: crypto.randomUUID(),
        role: 'student',
        content,
        created_at: new Date().toISOString(),
        modality: 'text',
    });
    await scrollToBottom();
    isPatientTyping.value = !noInterlocutor.value;

    // Rempli par les rappels du flux
    const current: { turn: Turn | null } = { turn: null };
    try {
        isStreaming.value = true;
        const final = await streamChatTurn(attemptId, content, {
            onStart: () => { current.turn = startTurn(studentMessage.id, 'text'); },
            onDelta: (text) => current.turn?.delta(text),
            onNote: (note) => current.turn?.note(note),
        }, { signal: pageController.signal });
        (current.turn ?? startTurn(studentMessage.id, 'text')).done(final);
    } catch (error) {
        current.turn?.fail();
        if (pageController.signal.aborted) return;
        // Le message n'a pas été transmis : marqué « Non envoyé », texte remis dans la saisie
        studentMessage.failed = true;
        if (!draft.value.trim()) draft.value = content;
        if (error instanceof ApiError && (error.status === 410 || error.status === 408)) {
            stationOver.value = true;
            void header.value?.expire();
        } else {
            showError('Message non envoyé', error);
        }
    } finally {
        isStreaming.value = false;
        isSendingMessage.value = false;
        isPatientTyping.value = false;
    }
}

function handleSendMessage(content: string) {
    void sendText(content);
}

function retryMessage(message: ChatMessage) {
    if (isSendingMessage.value) return;
    removeMessages([message.id]);
    if (draft.value.trim() === message.content.trim()) draft.value = '';
    void sendText(message.content);
}

// ============= MODE VOCAL (appuyer pour parler) =============

const voice = new VoiceClient(attemptId);
const voiceState = ref<'idle' | 'connecting' | 'recording' | 'transcribing'>('idle');
const isPatientSpeaking = ref(false);
const speakingStudent = ref<ChatMessage | null>(null); // bulle étudiant en cours de transcription
// Tours en attente de "done", dans l'ordre (le serveur les traite l'un après l'autre)
const voiceTurns: { turn: Turn; student: ChatMessage }[] = [];
let voiceUnavailableShown = false;

// ----- Consultation orale (mains libres) -----
const consulting = ref(false);
const consultationConnecting = ref(false);
const micLevel = ref(0);
const micMuted = ref(false);
const awaitingVoice = ref(false);
const consultationNotice = ref<string | null>(null);
const showTranscript = ref(readPreference());

function readPreference(): boolean {
    try {
        return localStorage.getItem('ecos.voice.showTranscript') === '1';
    } catch {
        return false;
    }
}

const consultationStatus = computed<ConsultationStatus>(() => {
    if (consultationConnecting.value) return 'connecting';
    if (isPatientSpeaking.value) return 'speaking';
    if (speakingStudent.value) return 'user_speaking';
    if (awaitingVoice.value) return 'thinking';
    return 'listening';
});

/** La conversation change encore : les lecteurs d'écran attendent la fin pour l'annoncer */
const conversationBusy = computed(() =>
    isStreaming.value || isPatientTyping.value || !!speakingStudent.value || awaitingVoice.value);
const typingStatus = computed(() => (isPatientTyping.value ? `${subject.value} répond…` : ''));

const examinerNotes = computed(() => messages.value.filter(m => m.role === 'examiner'));

voice.onLevel = (level) => { micLevel.value = micLevel.value * 0.5 + level * 0.5; };

async function startConsultation() {
    consulting.value = true;
    consultationConnecting.value = true;
    consultationNotice.value = null;
    try {
        await voice.startConversation();
    } catch (error) {
        consulting.value = false;
        showError('Consultation orale indisponible', error);
    } finally {
        consultationConnecting.value = false;
    }
}

function leaveConsultation() {
    voice.stopConversation();
    consulting.value = false;
    micMuted.value = false;
    voice.setMuted(false);
    scrollToBottom();
}

function toggleMute() {
    micMuted.value = !micMuted.value;
    voice.setMuted(micMuted.value);
}

function toggleTranscript() {
    showTranscript.value = !showTranscript.value;
    try {
        localStorage.setItem('ecos.voice.showTranscript', showTranscript.value ? '1' : '0');
    } catch {
        // préférence non mémorisée : sans conséquence
    }
    scrollToBottom();
}

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
        speakingStudent.value = newPendingStudent();
        voiceState.value = 'recording';
        scrollToBottom();
    } catch (error) {
        voiceState.value = 'idle';
        showError('Mode vocal indisponible', error);
    }
}

function newPendingStudent(): ChatMessage {
    return pushMessage({
        id: crypto.randomUUID(),
        role: 'student',
        content: '',
        created_at: new Date().toISOString(),
        modality: 'voice',
        pending: true,
    });
}

function eventText(event: VoiceEvent, key: string): string {
    const value = event[key];
    return typeof value === 'string' ? value : '';
}

function handleVoiceEvent(event: VoiceEvent) {
    switch (event.type) {
        case 'transcript_partial':
            // En mains libres, c'est le serveur qui détecte le début d'une phrase
            speakingStudent.value ??= newPendingStudent();
            speakingStudent.value.content = eventText(event, 'text');
            scrollToBottom();
            break;
        case 'transcript_final': {
            voiceState.value = 'idle';
            const student = speakingStudent.value;
            speakingStudent.value = null;
            if (!student) break;
            const text = eventText(event, 'text');
            if (!text) {
                removeMessages([student.id]);
                pushNotice("Je n'ai rien entendu. Vérifiez votre micro et réessayez.");
                break;
            }
            student.content = text;
            student.pending = false;
            consultationNotice.value = null;
            awaitingVoice.value = true;
            voiceTurns.push({ turn: startTurn(student.id, 'voice'), student });
            break;
        }
        case 'turn_cancelled': {
            // Faux départ : l'étudiant n'avait pas fini sa phrase ; elle continue
            const last = voiceTurns.pop();
            if (last) {
                last.turn.fail();
                last.student.pending = true;
                speakingStudent.value = last.student;
            }
            awaitingVoice.value = false;
            break;
        }
        case 'delta':
            voiceTurns[0]?.turn.delta(eventText(event, 'text'));
            break;
        case 'examiner_note':
            voiceTurns[0]?.turn.note(event as unknown as ExaminerNote);
            break;
        case 'done': {
            const final = event as unknown as ChatResponse;
            voiceTurns.shift()?.turn.done(final);
            if (final.blocked) {
                consultationNotice.value = final.patient_reply;
                awaitingVoice.value = false;
            } else if (final.silent) {
                awaitingVoice.value = false;   // personne ne répond : pas de voix à attendre
            }
            break;
        }
        case 'audio_end':
            awaitingVoice.value = false;
            break;
        case 'patient_interrupted': {
            // Coupure de parole enregistrée (comptée dans la correction)
            const cut = messages.value.find(m => (m.server_id ?? m.id) === event.message_id);
            if (cut) {
                cut.interrupted_by = eventText(event, 'reason');
                cut.spoken_content = eventText(event, 'spoken_content');
            }
            break;
        }
        case 'voice_unavailable': {
            const message = eventText(event, 'message') || 'La voix du patient est indisponible.';
            awaitingVoice.value = false;
            consultationNotice.value = message;
            if (!voiceUnavailableShown) pushNotice(message);
            voiceUnavailableShown = true;
            break;
        }
        case 'error': {
            const message = eventText(event, 'message') || 'Erreur du mode vocal.';
            if (speakingStudent.value) {
                // La transcription a échoué : rien n'a été envoyé
                removeMessages([speakingStudent.value.id]);
                speakingStudent.value = null;
            } else {
                voiceTurns.shift()?.turn.fail();
            }
            voiceState.value = 'idle';
            isPatientTyping.value = false;
            awaitingVoice.value = false;
            consultationNotice.value = message;
            pushNotice(message);
            break;
        }
        case 'closed':
            voiceState.value = 'idle';
            isPatientSpeaking.value = false;
            awaitingVoice.value = false;
            if (speakingStudent.value) {
                removeMessages([speakingStudent.value.id]);
                speakingStudent.value = null;
            }
            voiceTurns.splice(0).forEach(({ turn }) => turn.fail());
            if (consulting.value) {
                consulting.value = false;
                pushNotice('La connexion vocale a été interrompue.');
            }
            break;
    }
}

// ============= CYCLE DE VIE =============

onMounted(async () => {
    await Promise.all([loadMessages(), loadStationInfo()]);
});

onBeforeUnmount(() => {
    pageController.abort();
    voice.close();
});
</script>

<style scoped>
.chat-view {
    display: flex;
    flex-direction: column;
    min-height: 0;
    height: 100%;
}

.chat-body {
    display: flex;
    flex-direction: column;
    gap: 1rem;
    padding: 1rem;
    flex: 1;
    min-height: 0;
}

.message-container {
    display: flex;
    flex-direction: column;
    flex: 1;
    /* Toujours une zone de lecture, même au zoom 200 % : la page défile alors */
    min-height: 12rem;
    overflow-y: auto;
    padding: 0.5rem;
    scroll-behavior: smooth;
}

.message-container:focus-visible {
    outline: 3px solid #1d4ed8;
    outline-offset: 2px;
}

.loading {
    text-align: center;
    padding: 2rem;
    color: #4b5563;
}

.load-error :deep(.p-message-text) {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    flex-wrap: wrap;
}

.silent-hint {
    display: flex;
    gap: .5rem;
    align-items: center;
    padding: .5rem .75rem;
    border-radius: 8px;
    background: #f1f5f9;
    color: #334155;
    font-size: .9rem;
}

.station-over {
    margin: 0;
    padding: 0.5rem 0.75rem;
    border-radius: 8px;
    background: #343a40;
    color: #ffffff;
    font-weight: 600;
}

/* Indicateur « le patient écrit » */
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

/* Saisie : zone de texte + boutons micro */
.input-row {
    display: flex;
    align-items: center;
    gap: 0.5rem;
}

.input-box {
    flex: 1;
    min-width: 0;
    padding: .5rem;
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

@media (prefers-reduced-motion: reduce) {
    .typing-indicator span,
    .mic-button.recording {
        animation: none;
    }
    .message-container {
        scroll-behavior: auto;
    }
}

@media (max-width: 640px) {
    .chat-body {
        padding: 0.5rem 0;
    }
    .input-row {
        flex-wrap: wrap;
    }
    .input-box {
        flex-basis: 100%;
        padding: 0;
    }
}

.speaking-bar {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0 0.75rem;
    color: #374151;
    font-size: 0.9rem;
}

.message-container::-webkit-scrollbar {
    width: 8px;
}

.message-container::-webkit-scrollbar-track {
    background: #f1f1f1;
    border-radius: 10px;
}

.message-container::-webkit-scrollbar-thumb {
    background: #888;
    border-radius: 10px;
}
</style>
