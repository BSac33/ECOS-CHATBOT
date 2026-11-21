<script setup lang="ts">
// Mon compte : export des données personnelles et suppression du compte (RGPD)
import { nextTick, ref } from 'vue'
import { useRouter } from 'vue-router'
import Button from 'primevue/button'
import Message from 'primevue/message'
import Password from 'primevue/password'
import { useToast } from 'primevue/usetoast'
import { useAuthStore } from './stores/auth'
import { apiService } from './services/api'
import { errorMessage } from './services/http'
import { ROLE_LABELS } from './types'

const auth = useAuthStore()
const router = useRouter()
const toast = useToast()

// ---------- Export ----------
const exporting = ref(false)
const exportError = ref<string | null>(null)

/** Enregistre un fichier côté navigateur (lien temporaire). */
function saveFile(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}

async function exportData() {
  exporting.value = true
  exportError.value = null
  try {
    const blob = await apiService.exportMyData()
    saveFile(blob, 'mes-donnees-ecos.json')
    toast.add({ severity: 'success', summary: 'Export prêt', detail: 'Le fichier mes-donnees-ecos.json a été téléchargé.', life: 5000 })
  } catch (error) {
    exportError.value = `L'export n'a pas pu être réalisé. ${errorMessage(error)}`
  } finally {
    exporting.value = false
  }
}

// ---------- Suppression (deux étapes) ----------
const confirmingDelete = ref(false)
const password = ref('')
const deleting = ref(false)
const deleteError = ref<string | null>(null)
const confirmSection = ref<HTMLElement | null>(null)

async function askDelete() {
  confirmingDelete.value = true
  deleteError.value = null
  await nextTick()
  confirmSection.value?.querySelector<HTMLInputElement>('input')?.focus()
}

function cancelDelete() {
  confirmingDelete.value = false
  password.value = ''
  deleteError.value = null
}

async function deleteAccount() {
  if (!password.value) {
    deleteError.value = 'Saisissez votre mot de passe pour confirmer.'
    return
  }
  deleting.value = true
  deleteError.value = null
  try {
    await apiService.deleteMyAccount(password.value)
    password.value = ''
    // Compte supprimé : session locale vidée, cookie effacé par le serveur (ou expiré)
    await auth.logout()
    toast.add({ severity: 'success', summary: 'Compte supprimé', detail: 'Votre compte et vos données ont été supprimés.', life: 8000 })
    await router.replace({ name: 'login' })
  } catch (error) {
    // 409 (enseignant auteur de stations), mot de passe incorrect... : message du serveur
    deleteError.value = errorMessage(error)
  } finally {
    deleting.value = false
  }
}
</script>

<template>
  <div class="account-page">
    <h1>Mon compte</h1>

    <section v-if="auth.user" class="card" aria-labelledby="profile-title">
      <h2 id="profile-title">Profil</h2>
      <dl class="profile">
        <dt>Identifiant</dt><dd>{{ auth.user.username }}</dd>
        <template v-if="auth.user.full_name"><dt>Nom</dt><dd>{{ auth.user.full_name }}</dd></template>
        <template v-if="auth.user.email"><dt>Courriel</dt><dd>{{ auth.user.email }}</dd></template>
        <dt>Rôle</dt><dd>{{ ROLE_LABELS[auth.user.role] ?? auth.user.role }}</dd>
      </dl>
    </section>

    <section class="card" aria-labelledby="export-title">
      <h2 id="export-title">Exporter mes données</h2>
      <p>
        Téléchargez un fichier contenant vos informations de compte, vos passages (conversations) et leurs corrections.
      </p>
      <Message v-if="exportError" severity="error" :closable="false">{{ exportError }}</Message>
      <Button label="Exporter mes données" icon="pi pi-download" :loading="exporting" @click="exportData" />
    </section>

    <section class="card danger" aria-labelledby="delete-title">
      <h2 id="delete-title">Supprimer mon compte</h2>
      <p>
        La suppression est définitive : votre compte, vos passages et leurs corrections seront effacés.
        Pensez à exporter vos données avant.
      </p>
      <Button
        v-if="!confirmingDelete"
        label="Supprimer mon compte"
        icon="pi pi-trash"
        severity="danger"
        outlined
        @click="askDelete"
      />
      <div v-else ref="confirmSection" class="confirm">
        <p class="confirm-title"><strong>Confirmez la suppression définitive.</strong></p>
        <form class="confirm-form" @submit.prevent="deleteAccount">
          <label for="delete-password">Mot de passe</label>
          <Password
            v-model="password"
            input-id="delete-password"
            :input-props="{ autocomplete: 'current-password' }"
            :feedback="false"
            toggle-mask
            :invalid="!!deleteError"
          />
          <Message v-if="deleteError" severity="error" :closable="false">{{ deleteError }}</Message>
          <div class="confirm-actions">
            <Button type="button" label="Annuler" severity="secondary" text @click="cancelDelete" />
            <Button type="submit" label="Supprimer définitivement" icon="pi pi-trash" severity="danger" :loading="deleting" />
          </div>
        </form>
      </div>
    </section>
  </div>
</template>

<style scoped>
.account-page {
  max-width: 48rem;
  padding: 1rem 0 3rem;
}

.card {
  border: 1px solid #e2e8f0;
  border-radius: 12px;
  padding: 1.25rem 1.5rem;
  margin-bottom: 1.25rem;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 0.75rem;
}

.card h2 {
  margin: 0;
  font-size: 1.2rem;
}

.card p {
  margin: 0;
  color: #374151;
}

.card.danger {
  border-color: #fca5a5;
}

.profile {
  display: grid;
  grid-template-columns: max-content 1fr;
  gap: 0.35rem 1rem;
  margin: 0;
}

.profile dt {
  font-weight: 600;
  color: #374151;
}

.profile dd {
  margin: 0;
  overflow-wrap: anywhere;
}

.confirm {
  width: 100%;
  border-top: 1px solid #fecaca;
  padding-top: 0.75rem;
}

.confirm-title {
  margin-bottom: 0.5rem !important;
}

.confirm-form {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 0.5rem;
}

.confirm-form label {
  font-weight: 600;
  color: #374151;
}

.confirm-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
}
</style>
