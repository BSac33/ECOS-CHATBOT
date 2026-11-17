<template>
    <section class="consultation" aria-label="Consultation orale">
        <div class="stage">
            <!-- Patient : l'onde s'anime quand il parle -->
            <div class="avatar-wrap" :class="{ speaking: status === 'speaking', thinking: status === 'thinking' }">
                <span class="wave"></span>
                <span class="wave delay"></span>
                <div class="avatar"><i class="pi pi-user"></i></div>
            </div>
            <div class="patient-label">{{ props.who || 'Patient' }}</div>

            <p class="status" role="status" aria-live="polite">{{ statusText }}</p>

            <!-- Niveau du micro de l'étudiant -->
            <div class="mic-meter" :class="{ muted }" aria-hidden="true">
                <i :class="muted ? 'pi pi-microphone-slash' : 'pi pi-microphone'"></i>
                <span
                    v-for="i in 5"
                    :key="i"
                    class="bar"
                    :style="{ transform: `scaleY(${barScale(i)})` }"
                ></span>
            </div>

            <p class="hint">Conseil : utilisez un casque, le micro n'entendra pas la voix du patient.</p>
        </div>

        <!-- Avertissement hors personnage (message bloqué, voix indisponible...) -->
        <div v-if="notice" class="notice" role="alert">
            <i class="pi pi-info-circle"></i>
            <span>{{ notice }}</span>
        </div>

        <!-- Informations de l'examinateur : toujours visibles (constantes, ECG...) -->
        <div v-if="examinerNotes.length" class="examiner">
            <h3>Informations de l'examinateur</h3>
            <Message v-for="note in examinerNotes" :key="note.id" :message="note" />
        </div>

        <div class="controls">
            <Button
                :icon="muted ? 'pi pi-microphone-slash' : 'pi pi-microphone'"
                :label="muted ? 'Rétablir le micro' : 'Couper le micro'"
                :severity="muted ? 'danger' : 'secondary'"
                outlined
                @click="emit('toggle-mute')"
            />
            <Button
                v-if="status === 'speaking'"
                icon="pi pi-volume-off"
                label="Interrompre le patient"
                severity="secondary"
                outlined
                @click="emit('interrupt')"
            />
            <Button
                :icon="showTranscript ? 'pi pi-eye-slash' : 'pi pi-eye'"
                :label="showTranscript ? 'Masquer la transcription' : 'Afficher la transcription'"
                severity="secondary"
                text
                @click="emit('toggle-transcript')"
            />
            <Button
                icon="pi pi-pencil"
                label="Revenir à l'écrit"
                severity="secondary"
                text
                @click="emit('leave')"
            />
        </div>
    </section>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import Button from 'primevue/button';
import Message from './Message.vue';

export type ConsultationStatus = 'connecting' | 'listening' | 'user_speaking' | 'thinking' | 'speaking';

interface ChatMessage {
    id: string;
    role: 'student' | 'patient' | 'system' | 'examiner';
    content: string;
    created_at: string;
    attachment_id?: string | null;
    attachment_mime_type?: string | null;
    modality?: string;
}

const props = defineProps<{
    /** Nom de l'interlocuteur (« Patient », « Cardiologue de garde »...) */
    who?: string;
    status: ConsultationStatus;
    level: number;
    muted: boolean;
    showTranscript: boolean;
    examinerNotes: ChatMessage[];
    notice: string | null;
}>();
const subject = computed(() => {
    const who = props.who || 'Patient';
    if (who === 'Patient') return 'Le patient';
    if (who === 'Patiente') return 'La patiente';
    return who;
});

const emit = defineEmits<{
    'toggle-mute': [];
    'toggle-transcript': [];
    'interrupt': [];
    'leave': [];
}>();

const statusText = computed(() => {
    if (props.muted && props.status !== 'speaking') return 'Micro coupé';
    switch (props.status) {
        case 'connecting': return 'Connexion…';
        case 'user_speaking': return 'Vous parlez…';
        case 'thinking': return `${subject.value} réfléchit…`;
        case 'speaking': return `${subject.value} parle…`;
        default: return `${subject.value} vous écoute`;
    }
});

// Barres du vumètre : la barre centrale réagit le plus
const shape = [0.45, 0.75, 1, 0.75, 0.45];
function barScale(i: number) {
    const level = props.muted ? 0 : props.level;
    return Math.max(0.12, Math.min(1, level * shape[i - 1]! * 1.6));
}
</script>

<style scoped>
.consultation {
    display: flex;
    flex-direction: column;
    gap: 1rem;
    padding: 1.25rem;
    border-radius: 1rem;
    background: linear-gradient(180deg, #f3f7fb 0%, #ffffff 100%);
    border: 1px solid #e3e9f0;
}

.stage {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 0.6rem;
    padding: 1rem 0 0.5rem;
}

.avatar-wrap {
    position: relative;
    width: 7.5rem;
    height: 7.5rem;
    display: grid;
    place-items: center;
}

.avatar {
    position: relative;
    z-index: 1;
    width: 6rem;
    height: 6rem;
    border-radius: 50%;
    display: grid;
    place-items: center;
    background: #dbe7f3;
    color: #2f6fab;
    font-size: 2.6rem;
    box-shadow: 0 4px 14px rgba(47, 111, 171, 0.18);
}

.wave {
    position: absolute;
    inset: 0.75rem;
    border-radius: 50%;
    border: 3px solid rgba(47, 111, 171, 0.35);
    opacity: 0;
}

.speaking .wave {
    animation: wave 1.6s ease-out infinite;
}

.speaking .wave.delay {
    animation-delay: 0.8s;
}

.thinking .avatar {
    animation: breathe 1.8s ease-in-out infinite;
}

@keyframes wave {
    0% { transform: scale(1); opacity: 0.9; }
    100% { transform: scale(1.45); opacity: 0; }
}

@keyframes breathe {
    0%, 100% { transform: scale(1); }
    50% { transform: scale(1.04); }
}

.patient-label {
    font-weight: 600;
    color: #1d3d5c;
}

.status {
    margin: 0;
    font-size: 1.05rem;
    color: #495057;
    min-height: 1.5rem;
}

.mic-meter {
    display: flex;
    align-items: center;
    gap: 0.25rem;
    height: 2rem;
    color: #2e7d32;
}

.mic-meter.muted {
    color: #c62828;
}

.mic-meter .pi {
    margin-right: 0.4rem;
}

.bar {
    width: 0.35rem;
    height: 1.6rem;
    border-radius: 0.2rem;
    background: currentColor;
    transform-origin: center;
    transition: transform 0.08s linear;
}

.hint {
    margin: 0;
    font-size: 0.8rem;
    color: #868e96;
}

.notice {
    display: flex;
    gap: 0.5rem;
    align-items: flex-start;
    padding: 0.75rem 1rem;
    border-radius: 0.5rem;
    background: #fff4e5;
    color: #8a5300;
    font-size: 0.9rem;
}

.examiner h3 {
    margin: 0 0 0.5rem;
    font-size: 0.85rem;
    text-transform: uppercase;
    letter-spacing: 0.03em;
    color: #1d3d5c;
}

.examiner :deep(.message-bubble) {
    max-width: 100%;
}

.controls {
    display: flex;
    flex-wrap: wrap;
    justify-content: center;
    gap: 0.5rem;
}
</style>
