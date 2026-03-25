<template>
    <div class="written-exam-wrapper">
        <!-- Header avec timer (sans bouton Terminer) -->
        <ExamHeader :attempt-id="attemptId" @expired="handleTimeExpired" />

        <div class="written-exam-body">
            <!-- Panneau gauche : énoncé + iconographie -->
            <div class="left-panel">
                <!-- Instructions de la station -->
                <div v-if="studentInstructions" class="instructions-card">
                    <h3 class="section-title">
                        <i class="pi pi-file-edit"></i>
                        Consigne
                    </h3>
                    <p class="instructions-text">{{ studentInstructions }}</p>
                </div>

                <!-- Iconographie (images / documents montrés dès le début) -->
                <div v-if="iconography.length > 0" class="iconography-section">
                    <h3 class="section-title">
                        <i class="pi pi-image"></i>
                        Iconographie
                    </h3>

                    <div
                        v-for="attachment in iconography"
                        :key="attachment.id"
                        class="attachment-block"
                    >
                        <p class="attachment-label">{{ attachment.display_name }}</p>

                        <!-- Image (radio, ECG photo, etc.) -->
                        <img
                            v-if="attachment.kind === 'image'"
                            :src="attachment.file_url"
                            :alt="attachment.display_name"
                            class="attachment-image"
                            @click="openLightbox(attachment.file_url, attachment.display_name)"
                        />

                        <!-- PDF / document -->
                        <iframe
                            v-else-if="attachment.kind === 'document' && attachment.mime_type === 'application/pdf'"
                            :src="attachment.file_url"
                            class="attachment-pdf"
                            :title="attachment.display_name"
                        />

                        <!-- Fallback : lien téléchargement -->
                        <a
                            v-else
                            :href="attachment.file_url"
                            target="_blank"
                            class="attachment-download"
                        >
                            <i class="pi pi-download"></i>
                            Télécharger {{ attachment.display_name }}
                        </a>
                    </div>
                </div>

                <!-- Chargement iconographie -->
                <div v-if="isLoadingAttachments" class="loading-attachments">
                    <i class="pi pi-spin pi-spinner"></i>
                    Chargement de l'iconographie…
                </div>
            </div>

            <!-- Panneau droit : zone de réponse -->
            <div class="right-panel">
                <div class="answer-card">
                    <h3 class="section-title">
                        <i class="pi pi-pencil"></i>
                        Votre réponse
                    </h3>

                    <textarea
                        v-model="studentAnswer"
                        class="answer-textarea"
                        placeholder="Rédigez votre réponse ici…"
                        :disabled="isSubmitting || isExpired"
                        rows="18"
                    />

                    <div class="answer-footer">
                        <span class="char-count">{{ studentAnswer.length }} caractère(s)</span>

                        <button
                            class="submit-btn"
                            :disabled="isSubmitting || isExpired || !studentAnswer.trim()"
                            @click="handleSubmit"
                        >
                            <i v-if="isSubmitting" class="pi pi-spin pi-spinner"></i>
                            <i v-else class="pi pi-check-circle"></i>
                            {{ isSubmitting ? 'Envoi en cours…' : 'Soumettre ma réponse' }}
                        </button>
                    </div>

                    <p v-if="submitError" class="submit-error">{{ submitError }}</p>
                    <p v-if="isExpired" class="expired-notice">
                        <i class="pi pi-clock"></i>
                        Le temps est écoulé. Votre réponse a été soumise automatiquement.
                    </p>
                </div>
            </div>
        </div>

        <!-- Lightbox image -->
        <div v-if="lightbox.open" class="lightbox-overlay" @click="lightbox.open = false">
            <div class="lightbox-content" @click.stop>
                <button class="lightbox-close" @click="lightbox.open = false">
                    <i class="pi pi-times"></i>
                </button>
                <p class="lightbox-title">{{ lightbox.title }}</p>
                <img :src="lightbox.src" :alt="lightbox.title" class="lightbox-image" />
            </div>
        </div>
    </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { useRouter, useRoute } from 'vue-router';
import ExamHeader from './components/ExamHeader.vue';
import { apiService } from './services/api';
import type { ExamAttachment } from './services/api';

const route = useRoute();
const router = useRouter();
const attemptId = route.params.attemptId as string;

// ============= STATE =============

const studentInstructions = ref<string>('');
const studentAnswer = ref<string>('');
const iconography = ref<ExamAttachment[]>([]);
const isLoadingAttachments = ref(false);
const isSubmitting = ref(false);
const isExpired = ref(false);
const submitError = ref<string | null>(null);

const lightbox = ref<{ open: boolean; src: string; title: string }>({
    open: false,
    src: '',
    title: '',
});

// ============= FONCTIONS =============

async function loadCaseData() {
    try {
        // Récupère les instructions via la route case-info (déjà disponible)
        const caseInfo = await fetch(`/chat/attempts/${attemptId}/case-info`, {
            credentials: 'include'
        }).then(r => r.json());

        // Récupère les instructions étudiantes depuis la route publique du cas
        const caseDetails = await apiService.getCaseInstructions(caseInfo.case_id);
        studentInstructions.value = caseDetails.student_instructions;
    } catch (error) {
        console.error('Erreur chargement consignes:', error);
    }
}

async function loadIconography() {
    isLoadingAttachments.value = true;
    try {
        iconography.value = await apiService.getExamAttachments(attemptId);
    } catch (error) {
        console.error('Erreur chargement iconographie:', error);
    } finally {
        isLoadingAttachments.value = false;
    }
}

function openLightbox(src: string, title: string) {
    lightbox.value = { open: true, src, title };
}

async function handleSubmit() {
    if (!studentAnswer.value.trim()) return;

    submitError.value = null;
    isSubmitting.value = true;

    try {
        // 1. Enregistre la réponse écrite
        await apiService.submitWrittenAnswer(attemptId, studentAnswer.value);

        // 2. Finalise la tentative
        await apiService.finalizeAttempt(attemptId);

        // 3. Redirige vers le débriefing
        router.push(`/debrief/${attemptId}`);
    } catch (error) {
        console.error('Erreur soumission:', error);
        submitError.value = error instanceof Error ? error.message : 'Erreur lors de la soumission.';
    } finally {
        isSubmitting.value = false;
    }
}

async function handleTimeExpired() {
    isExpired.value = true;

    // Tenter de sauvegarder la réponse actuelle (même partielle) puis finaliser
    try {
        if (studentAnswer.value.trim()) {
            await apiService.submitWrittenAnswer(attemptId, studentAnswer.value);
        }
        await apiService.finalizeAttempt(attemptId);
    } catch (_) {
        // Finalisation silencieuse en fin de temps
    }

    // Petite pause pour que l'étudiant voie le message, puis rediriger
    setTimeout(() => {
        router.push(`/debrief/${attemptId}`);
    }, 3000);
}

// ============= LIFECYCLE =============

onMounted(async () => {
    await Promise.all([loadCaseData(), loadIconography()]);
});
</script>

<style scoped>
.written-exam-wrapper {
    display: flex;
    flex-direction: column;
    height: 100%;
    min-height: 0;
    background: #f8fafc;
}

.written-exam-body {
    display: flex;
    flex: 1;
    min-height: 0;
    gap: 1.5rem;
    padding: 1.5rem;
    overflow: hidden;
}

/* ====== PANNEAU GAUCHE ====== */
.left-panel {
    flex: 1;
    min-width: 0;
    display: flex;
    flex-direction: column;
    gap: 1.25rem;
    overflow-y: auto;
}

.instructions-card,
.answer-card {
    background: #ffffff;
    border-radius: 12px;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
    padding: 1.5rem;
}

.section-title {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    font-size: 1rem;
    font-weight: 700;
    color: #1e293b;
    margin: 0 0 1rem 0;
    padding-bottom: 0.75rem;
    border-bottom: 2px solid #e2e8f0;
}

.section-title i {
    color: #667eea;
}

.instructions-text {
    font-size: 1rem;
    line-height: 1.7;
    color: #334155;
    margin: 0;
    white-space: pre-wrap;
}

/* Iconographie */
.iconography-section {
    background: #ffffff;
    border-radius: 12px;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
    padding: 1.5rem;
}

.attachment-block {
    margin-bottom: 1.5rem;
}

.attachment-label {
    font-weight: 600;
    color: #475569;
    font-size: 0.9rem;
    margin: 0 0 0.5rem 0;
    text-transform: uppercase;
    letter-spacing: 0.04em;
}

.attachment-image {
    width: 100%;
    max-height: 60vh;
    object-fit: contain;
    border-radius: 8px;
    border: 1px solid #e2e8f0;
    cursor: zoom-in;
    transition: transform 0.2s ease;
}

.attachment-image:hover {
    transform: scale(1.01);
}

.attachment-pdf {
    width: 100%;
    height: 500px;
    border: 1px solid #e2e8f0;
    border-radius: 8px;
}

.attachment-download {
    display: inline-flex;
    align-items: center;
    gap: 0.4rem;
    color: #667eea;
    text-decoration: none;
    font-weight: 500;
    padding: 0.5rem 1rem;
    border: 1px solid #667eea;
    border-radius: 6px;
    transition: background 0.2s;
}

.attachment-download:hover {
    background: #f0f0ff;
}

.loading-attachments {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    color: #94a3b8;
    font-size: 0.9rem;
    padding: 1rem;
}

/* ====== PANNEAU DROIT ====== */
.right-panel {
    flex: 1;
    min-width: 0;
    display: flex;
    flex-direction: column;
}

.answer-card {
    flex: 1;
    display: flex;
    flex-direction: column;
}

.answer-textarea {
    flex: 1;
    width: 100%;
    min-height: 300px;
    resize: vertical;
    border: 1.5px solid #cbd5e1;
    border-radius: 8px;
    padding: 1rem;
    font-size: 1rem;
    font-family: inherit;
    line-height: 1.6;
    color: #1e293b;
    background: #fafafa;
    transition: border-color 0.2s, box-shadow 0.2s;
    box-sizing: border-box;
}

.answer-textarea:focus {
    outline: none;
    border-color: #667eea;
    box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.12);
    background: #fff;
}

.answer-textarea:disabled {
    background: #f1f5f9;
    color: #94a3b8;
    cursor: not-allowed;
}

.answer-footer {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-top: 1rem;
    gap: 1rem;
}

.char-count {
    font-size: 0.8rem;
    color: #94a3b8;
}

.submit-btn {
    display: inline-flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.75rem 1.75rem;
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    color: #ffffff;
    border: none;
    border-radius: 8px;
    font-size: 1rem;
    font-weight: 600;
    cursor: pointer;
    transition: opacity 0.2s, transform 0.1s;
}

.submit-btn:hover:not(:disabled) {
    opacity: 0.9;
    transform: translateY(-1px);
}

.submit-btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
    transform: none;
}

.submit-error {
    margin-top: 0.75rem;
    color: #dc2626;
    font-size: 0.9rem;
}

.expired-notice {
    margin-top: 0.75rem;
    display: flex;
    align-items: center;
    gap: 0.4rem;
    color: #b45309;
    font-size: 0.9rem;
    font-weight: 500;
}

/* ====== LIGHTBOX ====== */
.lightbox-overlay {
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.85);
    z-index: 1000;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 2rem;
}

.lightbox-content {
    position: relative;
    max-width: 90vw;
    max-height: 90vh;
    display: flex;
    flex-direction: column;
    align-items: center;
}

.lightbox-close {
    position: absolute;
    top: -2rem;
    right: 0;
    background: transparent;
    border: none;
    color: #ffffff;
    font-size: 1.5rem;
    cursor: pointer;
    padding: 0.25rem;
}

.lightbox-title {
    color: #ffffff;
    font-weight: 600;
    margin: 0 0 0.75rem 0;
}

.lightbox-image {
    max-width: 100%;
    max-height: 80vh;
    object-fit: contain;
    border-radius: 8px;
}

/* ====== RESPONSIVE ====== */
@media (max-width: 900px) {
    .written-exam-body {
        flex-direction: column;
        overflow-y: auto;
    }

    .left-panel,
    .right-panel {
        flex: none;
    }

    .answer-textarea {
        min-height: 200px;
    }
}
</style>
