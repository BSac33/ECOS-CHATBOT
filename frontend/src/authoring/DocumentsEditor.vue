<script setup lang="ts">
// Documents remis avec la vignette (ECG, imagerie...) : montrés à l'étudiant dès le début
import { ref } from 'vue'
import InputText from 'primevue/inputtext'
import Button from 'primevue/button'
import { authoringApi, newDocumentId, type StationDocument } from './api'

const documents = defineModel<StationDocument[]>({ required: true })
const props = defineProps<{ caseId: number }>()

const uploading = ref<string | null>(null)
const error = ref('')

function add() {
  documents.value.push({ id: newDocumentId(), label: `Document ${documents.value.length + 1} : `, attachment_id: null })
}

async function upload(doc: StationDocument, event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  uploading.value = doc.id
  error.value = ''
  try {
    const out = await authoringApi.uploadDocument(props.caseId, file, doc.label)
    doc.attachment_id = out.attachment_id
  } catch (e: any) {
    error.value = e.message
  } finally {
    uploading.value = null
    input.value = ''
  }
}
</script>

<template>
  <div class="documents">
    <article v-for="(doc, i) in documents" :key="doc.id" class="doc" :data-field="`station.documents[${i}]`">
      <a v-if="doc.attachment_id" :href="`/attachments/download/${doc.attachment_id}`" target="_blank" rel="noopener" class="thumb">
        <img :src="`/attachments/download/${doc.attachment_id}`" :alt="doc.label" />
      </a>
      <div v-else class="thumb empty"><i class="pi pi-image"></i></div>
      <div class="doc-body">
        <InputText v-model="doc.label" fluid placeholder="Document 1 : tracé-ECG" />
        <div class="doc-actions">
          <label class="file-button">
            <input type="file" accept="image/*,application/pdf" @change="upload(doc, $event)" />
            <span class="p-button p-button-sm p-button-outlined p-button-secondary">
              <i :class="uploading === doc.id ? 'pi pi-spin pi-spinner' : 'pi pi-upload'"></i>
              {{ doc.attachment_id ? 'Remplacer le fichier' : 'Choisir un fichier' }}
            </span>
          </label>
          <Button icon="pi pi-trash" text rounded severity="secondary" aria-label="Retirer le document" @click="documents.splice(i, 1)" />
        </div>
      </div>
    </article>
    <p v-if="error" class="error">{{ error }}</p>
    <Button label="Ajouter un document" icon="pi pi-plus" text size="small" @click="add" />
  </div>
</template>

<style scoped>
.documents { display: flex; flex-direction: column; gap: 0.5rem; align-items: flex-start; }
.doc { display: flex; gap: 0.75rem; align-items: center; width: 100%; border: 1px solid #e2e8f0; border-radius: 10px; padding: 0.5rem; box-sizing: border-box; }
.thumb { width: 7rem; height: 4.5rem; flex-shrink: 0; border-radius: 6px; overflow: hidden; background: #f1f5f9; display: flex; align-items: center; justify-content: center; }
.thumb img { width: 100%; height: 100%; object-fit: cover; }
.thumb.empty { color: #94a3b8; font-size: 1.4rem; }
.doc-body { flex: 1; display: flex; flex-direction: column; gap: 0.35rem; min-width: 0; }
.doc-actions { display: flex; align-items: center; gap: 0.25rem; }
.file-button input { position: absolute; width: 1px; height: 1px; opacity: 0; }
.file-button span { cursor: pointer; display: inline-flex; gap: 0.4rem; align-items: center; }
.error { color: #b91c1c; margin: 0; }
</style>
