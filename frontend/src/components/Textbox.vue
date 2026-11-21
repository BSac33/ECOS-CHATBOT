<template>
    <form class="textbox" @submit.prevent="handleSend">
        <label for="chat-input" class="sr-only">Votre message</label>
        <Textarea
            id="chat-input"
            v-model="value"
            auto-resize
            rows="2"
            fluid
            :maxlength="maxLength"
            :disabled="disabled"
            :aria-describedby="nearLimit ? 'chat-input-count' : undefined"
            placeholder="Tapez votre message…"
            @keydown.enter.exact.prevent="handleSend"
        />
        <Button
            type="submit"
            icon="pi pi-send"
            class="send-button"
            aria-label="Envoyer le message"
            title="Envoyer le message (Entrée)"
            :disabled="disabled || !value.trim()"
        />
        <p v-if="nearLimit" id="chat-input-count" class="count" aria-live="polite">
            {{ value.length }} / {{ maxLength }} caractères
        </p>
    </form>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import Textarea from 'primevue/textarea';
import Button from 'primevue/button';

/**
 * Zone de saisie du chat.
 * Le texte est un v-model : la vue le remet en place si l'envoi échoue.
 */
const props = withDefaults(defineProps<{
    disabled?: boolean;
    /** Taille maximale acceptée par le serveur (au-delà : 422) */
    maxLength?: number;
}>(), {
    disabled: false,
    maxLength: 2000,
});

const value = defineModel<string>({ default: '' });

const emit = defineEmits<{
    'send-message': [message: string];
}>();

// Compteur affiché à l'approche de la limite
const nearLimit = computed(() => value.value.length >= props.maxLength * 0.9);

function handleSend() {
    const trimmedValue = value.value.trim();
    if (!trimmedValue || props.disabled) {
        return;
    }
    emit('send-message', trimmedValue);
    value.value = '';
}
</script>

<style scoped>
.textbox {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 0.75rem;
    min-height: 0;
}

.textbox :deep(textarea) {
    flex: 1;
    min-width: 0;
}

.send-button {
    padding: 1rem;
    flex-shrink: 0;
}

.count {
    flex-basis: 100%;
    margin: 0;
    font-size: 0.8rem;
    color: #4b5563;
}
</style>
