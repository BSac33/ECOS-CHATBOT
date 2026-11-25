<template>
    <div class="written-station">
        <!-- Volet de gauche : énoncé et documents de la vignette -->
        <aside class="statement ecos-card" aria-labelledby="statement-title">
            <h2 id="statement-title" class="panel-title">
                <i class="pi pi-file" aria-hidden="true"></i> Énoncé
            </h2>
            <div class="statement-text">{{ statementText }}</div>

            <template v-if="documents.length">
                <h3 class="docs-title">
                    Documents <span class="docs-count">{{ documents.length }}</span>
                </h3>
                <ul class="doc-list">
                    <li v-for="doc in docs" :key="doc.id" class="doc">
                        <p class="doc-title">{{ doc.title }}</p>
                        <button
                            v-if="doc.kind === 'image'"
                            type="button"
                            class="doc-thumb"
                            :aria-label="`Agrandir : ${doc.title}`"
                            @click="openViewer(doc)"
                        >
                            <img :src="doc.url" :alt="doc.title" />
                            <span class="doc-zoom" aria-hidden="true"><i class="pi pi-search-plus"></i> Agrandir</span>
                        </button>
                        <audio v-else-if="doc.kind === 'audio'" :src="doc.url" controls preload="none" class="doc-media"></audio>
                        <video v-else-if="doc.kind === 'video'" :src="doc.url" controls preload="none" class="doc-media"></video>
                        <a :href="doc.url" target="_blank" rel="noopener" class="doc-link">
                            <i :class="doc.kind === 'pdf' ? 'pi pi-file-pdf' : 'pi pi-external-link'" aria-hidden="true"></i>
                            {{ doc.kind === 'pdf' ? 'Ouvrir le document' : 'Ouvrir dans un nouvel onglet' }}<span class="sr-only"> (nouvel onglet)</span>
                        </a>
                    </li>
                </ul>
            </template>
        </aside>

        <!-- À droite : la réponse, rédigée puis rendue en une fois -->
        <section class="answer ecos-card" aria-labelledby="answer-title">
            <div class="answer-head">
                <h2 id="answer-title" class="panel-title">
                    <i class="pi pi-pencil" aria-hidden="true"></i> Votre réponse
                </h2>
                <p id="answer-help" class="answer-help">
                    Rédigez une réponse complète et construite, comme si vous l'exposiez aux examinateurs.
                    Elle est rendue <strong>en une seule fois</strong> et ne peut plus être modifiée ensuite.
                    À la fin du temps, ce qui est écrit est rendu automatiquement.
                </p>
            </div>

            <label for="answer-input" class="sr-only">Votre réponse</label>
            <textarea
                id="answer-input"
                v-model="answer"
                class="answer-input"
                :maxlength="MAX_ANSWER_LENGTH"
                :disabled="locked"
                aria-describedby="answer-help answer-count"
                lang="fr"
                spellcheck="true"
                placeholder="Par exemple : 1. Lecture des documents  2. Interprétation  3. Diagnostic  4. Conduite à tenir"
            ></textarea>

            <div class="answer-foot">
                <p class="answer-status" aria-live="polite">
                    <i v-if="savedAt" class="pi pi-check-circle" aria-hidden="true"></i>{{ saveStatus }}
                </p>
                <p id="answer-count" class="answer-count" :class="{ near: nearLimit }">
                    {{ words }} mot{{ words > 1 ? 's' : '' }} · {{ answer.length.toLocaleString('fr-FR') }} /
                    {{ MAX_ANSWER_LENGTH.toLocaleString('fr-FR') }} caractères
                </p>
                <Button
                    label="Rendre ma réponse"
                    icon="pi pi-send"
                    :disabled="!answer.trim() || locked"
                    :loading="submitting"
                    @click="confirmVisible = true"
                />
            </div>
        </section>

        <Dialog
            v-model:visible="confirmVisible"
            modal
            header="Rendre votre réponse ?"
            :style="{ width: 'min(32rem, calc(100vw - 2rem))' }"
        >
            <p class="confirm-text">
                Votre réponse ({{ words }} mot{{ words > 1 ? 's' : '' }}) va être envoyée et la station se terminera.
                Vous ne pourrez plus la modifier.
            </p>
            <template #footer>
                <Button label="Continuer à rédiger" severity="secondary" text @click="confirmVisible = false" />
                <Button label="Rendre ma réponse" icon="pi pi-send" :loading="submitting" @click="submit()" />
            </template>
        </Dialog>

        <Dialog
            v-model:visible="viewerVisible"
            modal
            maximizable
            :header="viewer?.title ?? 'Document'"
            :style="{ width: 'min(84rem, calc(100vw - 2rem))' }"
        >
            <img v-if="viewer" :src="viewer.url" :alt="viewer.title" class="viewer-image" />
            <template #footer>
                <a v-if="viewer" :href="viewer.url" target="_blank" rel="noopener">
                    Ouvrir dans un nouvel onglet<span class="sr-only"> (nouvel onglet)</span>
                </a>
            </template>
        </Dialog>
    </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue';
import { useRouter } from 'vue-router';
import Button from 'primevue/button';
import Dialog from 'primevue/dialog';
import { useToast } from 'primevue/usetoast';
import { apiService } from '../services/api';
import { ApiError, attachmentUrl, errorMessage } from '../services/http';
import { MAX_ANSWER_LENGTH } from '../services/chat';
import type { ChatMessage } from '../types';

/**
 * Station sans interlocuteur (lecture d'ECG, analyse d'examens...) : l'énoncé et les documents
 * restent sous les yeux, la réponse complète est rédigée à droite puis rendue en une fois.
 * Le brouillon est gardé sur l'appareil (rechargement de la page, coupure réseau).
 */
const props = withDefaults(defineProps<{
    attemptId: string;
    instructions: string;
    /** Messages de l'examinateur portant un document (vignette) */
    documents: ChatMessage[];
    /** Temps écoulé ou station terminée */
    disabled?: boolean;
}>(), {
    disabled: false,
});

const router = useRouter();
const toast = useToast();

const STORAGE_KEY = `ecos.answer.${props.attemptId}`;
const answer = ref(readDraft());
const savedAt = ref<Date | null>(answer.value ? new Date() : null);
const submitting = ref(false);
const submitted = ref(false);
const confirmVisible = ref(false);
const locked = computed(() => props.disabled || submitting.value || submitted.value);

// Phrase « Sur la plateforme : … » des consignes : remplacée par l'aide du champ de réponse
const statementText = computed(() =>
    props.instructions.split('\n').filter(line => !line.trim().startsWith('Sur la plateforme')).join('\n').trim());

type DocKind = 'image' | 'pdf' | 'audio' | 'video' | 'other';
interface Doc { id: string; title: string; url: string; kind: DocKind }

function kindOf(mime: string | null | undefined): DocKind {
    const type = mime ?? '';
    if (type.startsWith('image/')) return 'image';
    if (type === 'application/pdf') return 'pdf';
    if (type.startsWith('audio/')) return 'audio';
    if (type.startsWith('video/')) return 'video';
    return 'other';
}

const docs = computed<Doc[]>(() => props.documents
    .filter(m => m.attachment_id)
    .map(m => ({
        id: m.id,
        title: m.content.replace(/^Document affiché\s*[–-]\s*/, '') || 'Document',
        url: attachmentUrl(m.attachment_id!),
        kind: kindOf(m.attachment_mime_type),
    })));

const viewer = ref<Doc | null>(null);
const viewerVisible = ref(false);
function openViewer(doc: Doc) {
    viewer.value = doc;
    viewerVisible.value = true;
}

const words = computed(() => answer.value.trim().split(/\s+/).filter(Boolean).length);
const nearLimit = computed(() => answer.value.length >= MAX_ANSWER_LENGTH * 0.9);

const saveStatus = computed(() => {
    if (submitted.value) return 'Réponse rendue.';
    if (!savedAt.value) return 'Brouillon enregistré automatiquement sur cet appareil.';
    return `Brouillon enregistré sur cet appareil à ${savedAt.value.toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' })}.`;
});

// ----- Brouillon local (confort : si le stockage est indisponible, rien ne casse) -----
function readDraft(): string {
    try {
        return localStorage.getItem(STORAGE_KEY) ?? '';
    } catch {
        return '';
    }
}

function writeDraft(text: string) {
    try {
        if (text) localStorage.setItem(STORAGE_KEY, text);
        else localStorage.removeItem(STORAGE_KEY);
        savedAt.value = text ? new Date() : null;
    } catch {
        // stockage indisponible (navigation privée) : le brouillon reste dans la page
    }
}

let saveTimer: number | undefined;
watch(answer, (text) => {
    window.clearTimeout(saveTimer);
    saveTimer = window.setTimeout(() => writeDraft(text), 500);
});
onBeforeUnmount(() => {
    window.clearTimeout(saveTimer);
    if (!submitted.value) writeDraft(answer.value);
});

// ----- Rendu -----
async function goToDebrief() {
    await router.push({ name: 'debrief', params: { attemptId: props.attemptId } });
}

/** Envoie la réponse ; true si la station est terminée (rendue maintenant ou déjà). */
async function send(auto: boolean): Promise<boolean> {
    const text = answer.value.trim();
    if (!text || submitted.value) return false;
    submitting.value = true;
    try {
        await apiService.submitAnswer(props.attemptId, text);
        submitted.value = true;
        window.clearTimeout(saveTimer);
        writeDraft('');
        confirmVisible.value = false;
        toast.add({
            severity: 'success',
            summary: auto ? 'Temps écoulé : votre réponse a été rendue.' : 'Réponse rendue.',
            detail: 'Passage au débriefing.',
            life: 6000,
        });
        await goToDebrief();
        return true;
    } catch (error) {
        if (error instanceof ApiError && error.status === 409) {
            // Déjà rendue (autre onglet) : la station est terminée
            submitted.value = true;
            confirmVisible.value = false;
            await goToDebrief();
            return true;
        }
        if (!auto) {
            toast.add({ severity: 'error', summary: 'Réponse non rendue', detail: errorMessage(error), life: 10000 });
        }
        return false;
    } finally {
        submitting.value = false;
    }
}

function submit() {
    void send(false);
}

/** Fin du temps (appelé par l'en-tête) : rend ce qui est écrit. */
function submitOnExpire(): Promise<boolean> {
    return send(true);
}

defineExpose({ submitOnExpire });
</script>

<style scoped>
.written-station {
    display: grid;
    grid-template-columns: minmax(19rem, 2fr) 3fr;
    gap: 1rem;
    min-height: 0;
}

.statement,
.answer {
    min-height: 0;
    padding: 1.1rem 1.25rem;
}

.statement {
    overflow-y: auto;
}

.panel-title {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    margin: 0 0 0.75rem;
    font-size: 1rem;
    font-weight: 650;
}

.panel-title .pi {
    color: var(--ecos-primary);
}

.statement-text {
    white-space: pre-wrap;
    line-height: 1.6;
    color: var(--ecos-text-2);
    font-size: 0.95rem;
}

.docs-title {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    margin: 1.5rem 0 0.75rem;
    font-size: 0.95rem;
    font-weight: 650;
}

.docs-count {
    display: inline-grid;
    place-items: center;
    min-width: 1.5rem;
    height: 1.5rem;
    padding: 0 0.4rem;
    border-radius: 999px;
    background: var(--ecos-primary-soft);
    color: var(--ecos-primary-strong);
    font-size: 0.8rem;
}

.doc-list {
    list-style: none;
    margin: 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: 1rem;
}

.doc {
    padding: 0.75rem;
    border: 1px solid var(--ecos-border);
    border-radius: 10px;
    background: var(--ecos-surface-muted);
}

.doc-title {
    margin: 0 0 0.5rem;
    font-size: 0.88rem;
    font-weight: 600;
    color: var(--ecos-text);
}

.doc-thumb {
    position: relative;
    display: block;
    width: 100%;
    padding: 0;
    border: 1px solid var(--ecos-border);
    border-radius: 8px;
    background: #ffffff;
    cursor: zoom-in;
    overflow: hidden;
}

.doc-thumb img {
    display: block;
    width: 100%;
    max-height: 22rem;
    object-fit: contain;
}

.doc-zoom {
    position: absolute;
    right: 0.5rem;
    bottom: 0.5rem;
    display: inline-flex;
    align-items: center;
    gap: 0.3rem;
    padding: 0.2rem 0.55rem;
    border-radius: 999px;
    background: rgba(15, 23, 42, 0.78);
    color: #ffffff;
    font-size: 0.78rem;
}

.doc-thumb:hover .doc-zoom,
.doc-thumb:focus-visible .doc-zoom {
    background: var(--ecos-primary-strong);
}

.doc-media {
    width: 100%;
}

.doc-link {
    display: inline-flex;
    align-items: center;
    gap: 0.35rem;
    margin-top: 0.5rem;
    font-size: 0.85rem;
}

.answer {
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
}

.answer-head .panel-title {
    margin-bottom: 0.35rem;
}

.answer-help {
    margin: 0;
    color: var(--ecos-muted);
    font-size: 0.88rem;
    line-height: 1.5;
}

.answer-input {
    flex: 1;
    min-height: 16rem;
    width: 100%;
    box-sizing: border-box;
    padding: 1rem 1.1rem;
    border: 1px solid var(--ecos-border-strong);
    border-radius: 10px;
    background: #ffffff;
    color: var(--ecos-text);
    font: inherit;
    font-size: 1rem;
    line-height: 1.65;
    resize: none;
}

.answer-input:focus {
    outline: none;
    border-color: var(--ecos-primary);
    box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.2);
}

.answer-input:disabled {
    background: var(--ecos-surface-muted);
    color: var(--ecos-text-2);
}

.answer-foot {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: 0.5rem 1rem;
}

.answer-status,
.answer-count {
    margin: 0;
    font-size: 0.82rem;
    color: var(--ecos-muted);
}

.answer-status {
    display: inline-flex;
    align-items: center;
    gap: 0.35rem;
    flex: 1;
    min-width: 12rem;
}

.answer-status .pi {
    color: var(--ecos-success);
}

.answer-count {
    font-variant-numeric: tabular-nums;
}

.answer-count.near {
    color: #92400e;
    font-weight: 600;
}

.confirm-text {
    margin: 0;
    line-height: 1.55;
}

.viewer-image {
    display: block;
    max-width: 100%;
    margin: 0 auto;
}

/* Tablette : énoncé au-dessus, réponse en dessous */
@media (max-width: 1024px) {
    .written-station {
        grid-template-columns: 1fr;
        grid-template-rows: minmax(0, 2fr) minmax(0, 3fr);
    }
}

/* Téléphone : la page défile */
@media (max-width: 640px) {
    .written-station {
        grid-template-rows: none;
    }
    .statement,
    .answer {
        padding: 0.9rem;
    }
    .answer-input {
        min-height: 18rem;
    }
}
</style>
