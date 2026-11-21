<template>
    <div class="message-wrapper" :class="alignmentClass">
        <div class="message-bubble" :class="[bubbleClass, { 'bubble-blocked': message.blocked, 'bubble-pending': message.pending, 'bubble-failed': message.failed }]">
            <span v-if="message.role === 'examiner'" class="message-label" aria-hidden="true">
                <i class="pi pi-clipboard"></i> Examinateur
            </span>
            <p class="message-content"><span class="sr-only">{{ speakerPrefix }}</span>{{ displayedContent }}</p>
            <span v-if="message.interrupted_by" class="message-cut">
                <i class="pi pi-exclamation-triangle" aria-hidden="true"></i>
                Coupé avant la fin<span class="sr-only"> : seule la partie prononcée est affichée</span>
            </span>
            <template v-if="documentUrl">
                <a v-if="isImage" :href="documentUrl" target="_blank" rel="noopener">
                    <img :src="documentUrl" :alt="message.content" class="message-attachment-preview" />
                    <span class="sr-only"> (s'ouvre dans un nouvel onglet)</span>
                </a>
                <a :href="documentUrl" target="_blank" rel="noopener" class="message-attachment-link">
                    <i class="pi pi-external-link" aria-hidden="true"></i> Ouvrir le document<span class="sr-only"> (nouvel onglet)</span>
                </a>
            </template>
            <span v-if="message.blocked" class="message-blocked-note">
                Message non transmis au patient
            </span>
            <span v-if="message.failed" class="message-failed">
                <i class="pi pi-exclamation-circle" aria-hidden="true"></i>
                <span>Non envoyé</span>
                <Button
                    label="Réessayer"
                    icon="pi pi-refresh"
                    size="small"
                    text
                    :disabled="retryDisabled"
                    :aria-label="`Réessayer d'envoyer : ${message.content}`"
                    @click="emit('retry', message)"
                />
            </span>
            <span class="message-timestamp">
                <i v-if="message.modality === 'voice'" class="pi pi-microphone" aria-hidden="true"></i>
                <span v-if="message.modality === 'voice'" class="sr-only">À l'oral, </span>
                <time :datetime="message.created_at">{{ formattedTime }}</time>
            </span>
        </div>
    </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import Button from 'primevue/button';
import { attachmentUrl } from '../services/http';
import type { ChatMessage } from '../types';

const props = withDefaults(defineProps<{
    message: ChatMessage;
    /** Nom de l'interlocuteur simulé (« Patient », « Patiente », « Cardiologue de garde »...) */
    interlocutor?: string;
    /** Bouton « Réessayer » désactivé (un envoi est déjà en cours) */
    retryDisabled?: boolean;
}>(), {
    interlocutor: 'Patient',
    retryDisabled: false,
});

const emit = defineEmits<{
    retry: [message: ChatMessage];
}>();

// Préfixe lu par les lecteurs d'écran (l'alignement et la couleur ne suffisent pas)
const speakerPrefix = computed(() => {
    switch (props.message.role) {
        case 'student': return 'Vous : ';
        case 'patient': return `${props.interlocutor || 'Patient'} : `;
        case 'examiner': return 'Examinateur : ';
        default: return 'Information : ';
    }
});

// Classe d'alignement selon le rôle
const alignmentClass = computed(() => {
    return props.message.role === 'student' ? 'align-right' : 'align-left';
});

// Classe de style de bulle selon le rôle
const bubbleClass = computed(() => {
    switch (props.message.role) {
        case 'student':
            return 'bubble-student';
        case 'system':
            return 'bubble-system';
        case 'examiner':
            return 'bubble-examiner';
        default:
            return 'bubble-patient';
    }
});

// Réplique coupée : seule la partie prononcée (ce que l'étudiant a entendu)
const displayedContent = computed(() => {
    if (props.message.pending && !props.message.content) return 'Je vous écoute…';
    if (props.message.interrupted_by && props.message.spoken_content) return props.message.spoken_content;
    return props.message.content;
});

// Document affiché par l'examinateur (ECG, imagerie, biologie...)
const documentUrl = computed(() =>
    props.message.attachment_id ? attachmentUrl(props.message.attachment_id) : null
);
const isImage = computed(() => (props.message.attachment_mime_type ?? '').startsWith('image/'));

// Heure d'affichage
const formattedTime = computed(() => {
    const date = new Date(props.message.created_at);
    if (Number.isNaN(date.getTime())) return '';
    return date.toLocaleTimeString('fr-FR', { hour: 'numeric', minute: 'numeric' });
});
</script>

<style scoped>
.message-wrapper {
    display: flex;
    margin-bottom: 0.75rem;
    padding: 0 0.5rem;
    animation: slideIn 0.2s ease-out;
}

@keyframes slideIn {
    from {
        opacity: 0;
        transform: translateY(10px);
    }
    to {
        opacity: 1;
        transform: translateY(0);
    }
}

@media (prefers-reduced-motion: reduce) {
    .message-wrapper {
        animation: none;
    }
}

.align-left {
    justify-content: flex-start;
}

.align-right {
    justify-content: flex-end;
}

.message-bubble {
    max-width: min(70%, 48rem);
    padding: 0.75rem 1rem;
    border-radius: 1rem;
    box-shadow: 0 1px 2px rgba(0, 0, 0, 0.1);
    word-wrap: break-word;
    overflow-wrap: break-word;
}

@media (max-width: 640px) {
    .message-bubble {
        max-width: 88%;
    }
}

/* Messages de l'étudiant : vert clair, à droite */
.bubble-student {
    background-color: #d4edda;
    border-bottom-right-radius: 0.25rem;
    color: #0f3d1a;
}

/* Messages du patient : gris clair, à gauche */
.bubble-patient {
    background-color: #e9ecef;
    border-bottom-left-radius: 0.25rem;
    color: #212529;
}

/* Messages système : blanc avec bordure, à gauche */
.bubble-system {
    background-color: #ffffff;
    border: 2px solid #6c757d;
    border-bottom-left-radius: 0.25rem;
    color: #374151;
}

/* Informations de l'examinateur (hors personnage) : bleu clair, à gauche */
.bubble-examiner {
    background-color: #e7f1fb;
    border-left: 4px solid #2f6fab;
    border-bottom-left-radius: 0.25rem;
    color: #1d3d5c;
}

/* Message étudiant refusé par les garde-fous */
.bubble-blocked {
    border: 1px dashed #4b5563;
}

.bubble-blocked .message-content {
    text-decoration: line-through;
}

/* Message étudiant non envoyé (réseau, serveur) */
.bubble-failed {
    border: 2px dashed #b91c1c;
}

.message-failed {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: 0.35rem;
    margin-top: 0.25rem;
    font-size: 0.85rem;
    font-weight: 600;
    color: #991b1b;
}

.message-failed :deep(.p-button) {
    color: #991b1b;
    padding: 0.15rem 0.4rem;
}

.message-label {
    display: block;
    margin-bottom: 0.25rem;
    font-size: 0.75rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.03em;
}

.message-cut {
    display: block;
    margin-top: 0.25rem;
    font-size: 0.8rem;
    color: #92400e;
}

/* Transcription vocale en cours */
.bubble-pending .message-content {
    font-style: italic;
}

.message-timestamp .pi-microphone {
    font-size: 0.7rem;
    margin-right: 0.2rem;
}

.message-attachment-preview {
    display: block;
    max-width: 100%;
    max-height: 320px;
    margin-top: 0.5rem;
    border-radius: 0.5rem;
}

.message-attachment-link {
    display: inline-block;
    margin-top: 0.5rem;
    font-size: 0.85rem;
}

.message-blocked-note {
    display: block;
    margin-top: 0.25rem;
    font-size: 0.8rem;
    font-style: italic;
}

.message-content {
    margin: 0;
    font-size: 0.95rem;
    line-height: 1.4;
    white-space: pre-wrap;
}

.message-timestamp {
    display: block;
    margin-top: 0.25rem;
    font-size: 0.75rem;
    text-align: right;
}
</style>
