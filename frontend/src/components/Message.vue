<template>
    <div class="message-wrapper" :class="alignmentClass">
        <div class="message-bubble" :class="[bubbleClass, { 'bubble-blocked': message.blocked, 'bubble-pending': message.pending, 'bubble-failed': message.failed }]">
            <span v-if="label" class="message-label" aria-hidden="true">
                <i v-if="labelIcon" :class="labelIcon"></i> {{ label }}
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

// Étiquette visible au-dessus de la bulle (l'étudiant n'en a pas : c'est lui, à droite)
const label = computed(() => {
    switch (props.message.role) {
        case 'patient': return props.interlocutor || 'Patient';
        case 'examiner': return 'Examinateur';
        case 'system': return 'Consignes';
        default: return '';
    }
});
const labelIcon = computed(() => {
    switch (props.message.role) {
        case 'examiner': return 'pi pi-clipboard';
        case 'system': return 'pi pi-file';
        default: return '';
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
    margin-bottom: 0.85rem;
    animation: slideIn 0.18s ease-out;
}

@keyframes slideIn {
    from {
        opacity: 0;
        transform: translateY(6px);
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
    max-width: min(75%, 46rem);
    padding: 0.65rem 0.95rem;
    border-radius: 16px;
    overflow-wrap: break-word;
}

@media (max-width: 640px) {
    .message-bubble {
        max-width: 90%;
    }
}

/* Étudiant : bleu, à droite */
.bubble-student {
    background: var(--ecos-primary);
    color: #ffffff;
    border-bottom-right-radius: 4px;
}

.bubble-student .message-timestamp {
    color: #ffffff;
}

/* Patient ou professionnel simulé : bulle blanche, à gauche */
.bubble-patient {
    background: var(--ecos-surface);
    border: 1px solid var(--ecos-border);
    border-bottom-left-radius: 4px;
    color: var(--ecos-text);
}

/* Consignes de la station : encart sur toute la largeur */
.bubble-system {
    max-width: 100%;
    width: 100%;
    background: var(--ecos-primary-soft);
    border: 1px solid var(--ecos-primary-border);
    border-radius: var(--ecos-radius);
    color: var(--ecos-text);
}

.bubble-system .message-label {
    color: var(--ecos-primary-strong);
}

/* Examinateur (hors personnage) : encart neutre avec liseré */
.bubble-examiner {
    background: var(--ecos-surface-muted);
    border: 1px solid var(--ecos-border);
    border-left: 3px solid #475569;
    border-radius: 10px;
    color: var(--ecos-text);
}

/* Message étudiant refusé par les garde-fous */
.bubble-blocked {
    background: var(--ecos-surface-muted);
    color: var(--ecos-text-2);
    border: 1px dashed #64748b;
}

.bubble-blocked .message-content {
    text-decoration: line-through;
}

.bubble-blocked .message-timestamp {
    color: var(--ecos-muted);
}

/* Message étudiant non envoyé (réseau, serveur) */
.bubble-failed {
    background: var(--ecos-danger-soft);
    color: var(--ecos-text);
    border: 1px dashed var(--ecos-danger);
}

.bubble-failed .message-timestamp {
    color: var(--ecos-muted);
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
    display: flex;
    align-items: center;
    gap: 0.35rem;
    margin-bottom: 0.25rem;
    font-size: 0.75rem;
    font-weight: 650;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    color: var(--ecos-muted);
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
    max-height: 340px;
    margin-top: 0.5rem;
    border-radius: 8px;
    border: 1px solid var(--ecos-border);
    background: #ffffff;
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
    line-height: 1.5;
    white-space: pre-wrap;
}

.message-timestamp {
    display: block;
    margin-top: 0.2rem;
    font-size: 0.72rem;
    text-align: right;
    color: var(--ecos-muted);
}
</style>
