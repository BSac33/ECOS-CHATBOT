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

            <!-- Composant de saisie fixé en bas -->
            <Textbox 
                style="padding:.5rem;" 
                @send-message="handleSendMessage"
                :disabled="isSendingMessage"
            />
        </div>
    </div>
</template>

<script setup lang="ts">
import { ref, onMounted, nextTick } from 'vue';
import { useRoute } from 'vue-router';
import ChatHeader from './components/ChatHeader.vue';
import Message from './components/Message.vue';
import Textbox from './components/Textbox.vue';
import { apiService } from './services/api';

// ============= INTERFACES =============

/**
 * Interface correspondant au format de message du backend
 * Compatible avec le composant Message.vue
 */
interface ChatMessage {
    id: string;
    role: 'student' | 'patient' | 'system';
    content: string;
    created_at: string;
}

/**
 * Format de réponse de l'API lors de l'envoi d'un message
 */
interface ChatResponse {
    patient_reply: string;
    attachments?: string[];
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

/**
 * Gère l'envoi d'un nouveau message depuis le composant Textbox
 * Implémente une mise à jour optimiste pour une UX réactive
 * 
 * @param messageContent - Le contenu du message saisi par l'étudiant
 */
async function handleSendMessage(messageContent: string) {
    if (!messageContent.trim() || isSendingMessage.value) {
        return;
    }
    
    try {
        isSendingMessage.value = true;
        
        // ===== MISE À JOUR OPTIMISTE =====
        // Créer immédiatement le message de l'étudiant dans l'UI
        // sans attendre la réponse du serveur
        const studentMessage: ChatMessage = {
            id: crypto.randomUUID(), // ID temporaire
            role: 'student',
            content: messageContent,
            created_at: new Date().toISOString()
        };
        
        // Ajouter à l'array réactive (mise à jour immédiate de l'UI)
        messages.value.push(studentMessage);
        await scrollToBottom();
        
        // ===== APPEL API =====
        // Activer l'indicateur de frappe pendant l'attente
        isPatientTyping.value = true;
        
        // POST /chat/attempts/{attemptId}/chat
        const response = await fetch(`/chat/attempts/${attemptId}/chat`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            credentials: 'include',
            body: JSON.stringify({ message: messageContent })
        });
        
        if (!response.ok) {
            const error = await response.json().catch(() => ({ detail: 'Erreur réseau' }));
            throw new Error(error.detail || 'Erreur lors de l\'envoi du message');
        }
        
        const chatResponse: ChatResponse = await response.json();
        
        // ===== AJOUTER LA RÉPONSE DU PATIENT =====
        const patientMessage: ChatMessage = {
            id: crypto.randomUUID(), // ID unique pour la réponse
            role: 'patient',
            content: chatResponse.patient_reply,
            created_at: new Date().toISOString()
        };
        
        messages.value.push(patientMessage);
        await scrollToBottom();
        
        // TODO: Gérer les attachments si présents
        // if (chatResponse.attachments) { ... }
        
    } catch (error) {
        console.error('Erreur lors de l\'envoi du message:', error);
        
        // En cas d'erreur, on pourrait :
        // - Retirer le message optimiste de l'array
        // - Afficher un indicateur d'erreur sur le message
        // - Permettre un retry
        
        alert(`Erreur: ${error instanceof Error ? error.message : 'Erreur inconnue'}`);
        
    } finally {
        isSendingMessage.value = false;
        isPatientTyping.value = false;
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