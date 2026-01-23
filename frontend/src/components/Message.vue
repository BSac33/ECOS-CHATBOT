<template>
    <div class="message-wrapper" :class="alignmentClass">
        <div class="message-bubble" :class="bubbleClass">
            <p class="message-content">{{ message.content }}</p>
            <span class="message-timestamp">{{ formattedTime }}</span>
        </div>
    </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';

// Interface TypeScript correspondant à la classe Message du backend
interface ChatMessage {
    id: string;
    role: 'student' | 'patient' | 'system';
    content: string;
    created_at: string;
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
        default:
            return 'bubble-patient';
    }
});

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
