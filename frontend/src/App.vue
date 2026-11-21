<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { RouterLink, RouterView, useRoute, useRouter } from 'vue-router'
import Drawer from 'primevue/drawer'
import Button from 'primevue/button'
import Toast from 'primevue/toast'
import { useAuthStore } from './stores/auth'
import { isTeacher } from './authoring/api'

const visible = ref(false)
const loggingOut = ref(false)
const auth = useAuthStore()
const route = useRoute()
const router = useRouter()
const canAuthor = computed(() => isTeacher(auth.user))
const mainView = ref<HTMLElement | null>(null)

function close() {
  visible.value = false
}

async function logout() {
  loggingOut.value = true
  try {
    await auth.logout()
  } finally {
    loggingOut.value = false
    visible.value = false
  }
  await router.replace({ name: 'login' })
}

// Changement de page : retour en haut, et le focus revient au début du contenu (lecteurs d'écran, clavier)
let firstNavigation = true
watch(() => route.path, async () => {
  await nextTick()
  if (mainView.value) mainView.value.scrollTop = 0
  if (firstNavigation) {
    firstNavigation = false
    return
  }
  mainView.value?.focus({ preventScroll: true })
})
</script>

<template>
  <a class="skip-link" href="#contenu">Aller au contenu</a>
  <div class="app-shell">
    <div class="floating-menu-button" :class="{ 'menu-open': visible }">
      <Button
        icon="pi pi-bars"
        rounded
        aria-label="Ouvrir le menu principal"
        :aria-expanded="visible"
        @click="visible = true"
      />
    </div>

    <Drawer v-model:visible="visible" header="Menu principal">
      <nav aria-label="Menu principal">
        <ul class="menu-list">
          <template v-if="auth.isAuthenticated">
            <li><RouterLink to="/" @click="close">Stations</RouterLink></li>
            <li v-if="canAuthor"><RouterLink to="/atelier" @click="close">Atelier de stations</RouterLink></li>
            <li><RouterLink to="/compte" @click="close">Mon compte</RouterLink></li>
            <li>
              <Button
                label="Se déconnecter"
                icon="pi pi-sign-out"
                severity="secondary"
                text
                class="logout"
                :loading="loggingOut"
                @click="logout"
              />
            </li>
          </template>
          <li v-else><RouterLink to="/login" @click="close">Connexion</RouterLink></li>
        </ul>
      </nav>
      <p v-if="auth.isAuthenticated" class="menu-user">Connecté : {{ auth.displayName }}</p>
    </Drawer>

    <main id="contenu" ref="mainView" class="main-view" tabindex="-1">
      <RouterView />
    </main>

    <Toast position="top-right" />
  </div>
</template>

<style>
.app-shell {
  height: 100%;
  display: flex;
  flex-direction: column;
  min-height: 0;
}

/* Lien d'évitement : visible seulement au clavier */
.skip-link {
  position: absolute;
  left: 0.5rem;
  top: -3rem;
  z-index: 2000;
  padding: 0.5rem 1rem;
  background: #ffffff;
  color: #1e3a8a;
  border: 2px solid #1e3a8a;
  border-radius: 6px;
}
.skip-link:focus {
  top: 0.5rem;
}

/* Bouton du menu, fixe en haut à gauche */
.floating-menu-button {
  position: fixed;
  top: 1rem;
  left: 1rem;
  z-index: 1000;
  transition: opacity 0.3s ease;
}

/* Masquer le bouton quand le menu est ouvert */
.floating-menu-button.menu-open {
  opacity: 0;
  pointer-events: none;
}

.menu-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.menu-list a {
  font-size: 1.05rem;
}

.menu-list .logout {
  padding-left: 0;
  font-size: 1.05rem;
}

.menu-user {
  margin-top: 2rem;
  color: #475569;
  font-size: 0.9rem;
}

/* Défilement dans la zone principale (zoom 200 %, petits écrans) */
.main-view {
  flex: 1;
  min-height: 0;
  padding-left: 5rem;
  padding-right: 5rem;
  overflow-y: auto;
  overflow-x: auto;
}

.main-view:focus {
  outline: none;
}

/* Tablette : marges réduites */
@media (max-width: 960px) {
  .main-view {
    padding-left: 4.5rem;
    padding-right: 1.5rem;
  }
}

/* Téléphone : le bouton reste en haut à gauche, le contenu prend toute la largeur dessous */
@media (max-width: 640px) {
  .floating-menu-button {
    top: 0.5rem;
    left: 0.5rem;
  }

  .main-view {
    padding: 3.75rem 0.75rem 0;
  }
}

@media (prefers-reduced-motion: reduce) {
  .floating-menu-button {
    transition: none;
  }
}
</style>
