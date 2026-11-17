<template>
    <div class="message-wrapper" :class="alignmentClass">
        <div class="message-bubble" :class="[bubbleClass, { 'bubble-blocked': message.blocked, 'bubble-pending': message.pending }]">
            <span v-if="message.role === 'examiner'" class="message-label">
                <i class="pi pi-clipboard"></i> Examinateur
            </span>
            <p class="message-content">{{ displayedContent }}</p>
            <span v-if="message.interrupted_by" class="message-cut" title="Vous avez coupé la parole au patient : seule la partie prononcée est affichée">
                <i class="pi pi-exclamation-triangle"></i> Coupé avant la fin
            </span>
            <template v-if="attachmentUrl">
                <a v-if="isImage" :href="attachmentUrl" target="_blank" rel="noopener">
                    <img :src="attachmentUrl" :alt="message.content" class="message-attachment-preview" />
                </a>
                <a :href="attachmentUrl" target="_blank" rel="noopener" class="message-attachment-link">
                    <i class="pi pi-external-link"></i> Ouvrir le document
                </a>
            </template>
            <span v-if="message.blocked" class="message-blocked-note">
                Message non transmis au patient
            </span>
            <span class="message-timestamp">
                <i v-if="message.modality === 'voice'" class="pi pi-microphone" title="Échange à l'oral"></i>
                {{ formattedTime }}
            </span>
        </div>
    </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';

// Interface TypeScript correspondant à la classe Message du backend
interface ChatMessage {
    id: string;
    role: 'student' | 'patient' | 'system' | 'examiner';
    content: string;
    created_at: string;
    attachment_id?: string | null;
    attachment_mime_type?: string | null;
    modality?: string;
    blocked?: boolean;
    pending?: boolean;
    interrupted_by?: string | null;
    spoken_content?: string | null;
}

// Props du composant
const props = defineProps<{
    message: ChatMessage;
}>();

// Classe d'alignement selon le rôle
const alignmentClass = computed(() => {
    return props.message.role === 'student' ? 'align-right' : 'align-left';
});

// Classe de style de bulle selon le rôle
const bubbleClass = computed(() => {
    switch (props.message.role) {
        case 'student':
            return 'bubble-student';
        case 'patient':
            return 'bubble-patient';
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
const attachmentUrl = computed(() =>
    props.message.attachment_id ? `/attachments/download/${props.message.attachment_id}` : null
);
const isImage = computed(() => (props.message.attachment_mime_type ?? '').startsWith('image/'));

// Formatage de l'heure d'affichage
const formattedTime = computed(() => {
    const date = new Date(props.message.created_at);
    return date.toLocaleTimeString('fr-FR', { 
        hour: '2-digit', 
        minute: '2-digit' 
    });
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

.align-left {
    justify-content: flex-start;
}

.align-right {
    justify-content: flex-end;
}

.message-bubble {
    max-width: 70%;
    padding: 0.75rem 1rem;
    border-radius: 1rem;
    box-shadow: 0 1px 2px rgba(0, 0, 0, 0.1);
    word-wrap: break-word;
    overflow-wrap: break-word;
}

/* Style pour les messages de l'étudiant - vert clair, aligné à droite */
.bubble-student {
    background-color: #d4edda;
    border-bottom-right-radius: 0.25rem;
    color: #155724;
}

/* Style pour les messages du patient - gris clair, aligné à gauche */
.bubble-patient {
    background-color: #e9ecef;
    border-bottom-left-radius: 0.25rem;
    color: #212529;
}

/* Style pour les messages système - blanc avec bordure prononcée, aligné à gauche */
.bubble-system {
    background-color: #ffffff;
    border: 2px solid #6c757d;
    border-bottom-left-radius: 0.25rem;
    color: #495057;
}

/* Informations de l'examinateur (hors personnage) - bleu clair, aligné à gauche */
.bubble-examiner {
    background-color: #e7f1fb;
    border-left: 4px solid #2f6fab;
    border-bottom-left-radius: 0.25rem;
    color: #1d3d5c;
}

/* Message étudiant refusé par les garde-fous */
.bubble-blocked {
    opacity: 0.6;
}

.bubble-blocked .message-content {
    text-decoration: line-through;
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
    font-size: 0.75rem;
    color: #b45309;
}

/* Transcription vocale en cours */
.bubble-pending .message-content {
    font-style: italic;
    opacity: 0.75;
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
    font-size: 0.75rem;
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
    opacity: 0.6;
    text-align: right;
}
</style>
