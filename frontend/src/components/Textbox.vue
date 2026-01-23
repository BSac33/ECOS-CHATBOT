
<template>
    <div class="card flex justify-center" style="display:flex; min-height:0; align-items:center; gap:1rem; justify-content:flex-end; ">
        <Textarea 
            v-model="value" 
            auto-resize  
            rows="2"
            fluid 
            :disabled="disabled"
            @keydown.enter.exact.prevent="handleSend"
            placeholder="Tapez votre message..."
        />
        <Button 
            icon="pi pi-send" 
            style="padding: 1rem; padding-left: 1rem; padding-right: 1rem;" 
            @click="handleSend"
            :disabled="disabled || !value.trim()"
        />
    </div>
</template>

<script setup lang="ts">
import { ref } from 'vue';
import Textarea from 'primevue/textarea';
import Button from 'primevue/button';

// ============= PROPS =============

/**
 * Props du composant
 * @property disabled - Désactive le textarea et le bouton pendant l'envoi
 */
interface TextboxProps {
    disabled?: boolean;
}

const props = withDefaults(defineProps<TextboxProps>(), {
    disabled: false
});

// ============= ÉMISSIONS D'ÉVÉNEMENTS =============

/**
 * Événements émis par le composant
 * @event send-message - Émis quand l'utilisateur envoie un message
 */
const emit = defineEmits<{
    'send-message': [message: string];
}>();

// ============= STATE RÉACTIF =============

/**
 * Contenu du textarea lié avec v-model
 */
const value = ref('');

// ============= FONCTIONS =============

/**
 * Gère l'envoi du message
 * - Vérifie que le message n'est pas vide
 * - Émet l'événement 'send-message' avec le contenu
 * - Vide le textarea après l'envoi
 */
function handleSend() {
    const trimmedValue = value.value.trim();
    
    // Ne rien faire si le message est vide ou si le composant est désactivé
    if (!trimmedValue || props.disabled) {
        return;
    }
    
    // Émettre l'événement avec le contenu du message
    emit('send-message', trimmedValue);
    
    // Vider le textarea après l'envoi
    value.value = '';
}
</script>
