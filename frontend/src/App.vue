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

/** Page de connexion : plein écran, sans barre */
const bare = computed(() => route.name === 'login')
/** Station en cours : toute la hauteur de la fenêtre, défilement interne */
const fullHeight = computed(() => route.name === 'chat')

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
    <header v-if="!bare" class="app-bar">
      <div class="app-bar-inner">
        <Button
          class="menu-toggle"
          icon="pi pi-bars"
          text
          rounded
          severity="secondary"
          aria-label="Ouvrir le menu principal"
          :aria-expanded="visible"
          @click="visible = true"
        />
        <RouterLink to="/" class="brand" aria-label="ECOS Entraînement, accueil">
          <span class="brand-mark" aria-hidden="true">E</span>
          <span class="brand-name">ECOS <span class="brand-sub">Entraînement</span></span>
        </RouterLink>

        <nav v-if="auth.isAuthenticated" class="app-nav" aria-label="Navigation principale">
          <RouterLink to="/" exact-active-class="active">Stations</RouterLink>
          <RouterLink v-if="canAuthor" to="/atelier" active-class="active">Atelier</RouterLink>
          <RouterLink to="/compte" active-class="active">Mon compte</RouterLink>
        </nav>

        <div class="app-user">
          <template v-if="auth.isAuthenticated">
            <span class="user-name"><i class="pi pi-user" aria-hidden="true"></i>{{ auth.displayName }}</span>
            <Button
              label="Se déconnecter"
              icon="pi pi-sign-out"
              severity="secondary"
              text
              size="small"
              :loading="loggingOut"
              @click="logout"
            />
          </template>
          <RouterLink v-else to="/login">Connexion</RouterLink>
        </div>
      </div>
    </header>

    <!-- Petits écrans : la navigation passe dans un tiroir -->
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
      <RouterView v-if="bare" />
      <div v-else class="page-frame" :class="{ 'full-height': fullHeight }">
        <RouterView />
      </div>
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

/* ---------- Barre de l'application ---------- */
.app-bar {
  flex-shrink: 0;
  background: var(--ecos-surface);
  border-bottom: 1px solid var(--ecos-border);
}

.app-bar-inner {
  display: flex;
  align-items: center;
  gap: 1.5rem;
  height: 3.5rem;
  padding: 0 1.5rem;
}

.menu-toggle {
  display: none !important;
}

.brand {
  display: inline-flex;
  align-items: center;
  gap: 0.6rem;
  color: var(--ecos-text);
  text-decoration: none;
  font-weight: 700;
  white-space: nowrap;
}
.brand:hover {
  color: var(--ecos-text);
}

.brand-mark {
  display: inline-grid;
  place-items: center;
  width: 2rem;
  height: 2rem;
  border-radius: 8px;
  background: var(--ecos-primary);
  color: #ffffff;
  font-size: 1rem;
}

.brand-sub {
  font-weight: 500;
  color: var(--ecos-muted);
}

.app-nav {
  display: flex;
  align-items: stretch;
  gap: 0.25rem;
  height: 100%;
}

.app-nav a {
  display: inline-flex;
  align-items: center;
  padding: 0 0.85rem;
  color: var(--ecos-text-2);
  font-weight: 500;
  text-decoration: none;
  border-bottom: 2px solid transparent;
  margin-bottom: -1px;
}
.app-nav a:hover {
  color: var(--ecos-text);
  background: var(--ecos-surface-muted);
}
.app-nav a.active {
  color: var(--ecos-primary-strong);
  border-bottom-color: var(--ecos-primary);
}

.app-user {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-left: auto;
  white-space: nowrap;
}

.user-name {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  color: var(--ecos-text-2);
  font-size: 0.9rem;
}
.user-name .pi {
  color: var(--ecos-muted);
}

/* ---------- Menu (tiroir) ---------- */
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
  color: var(--ecos-muted);
  font-size: 0.9rem;
}

/* ---------- Contenu ---------- */
.main-view {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  overflow-x: auto;
}

.main-view:focus {
  outline: none;
}

.page-frame {
  max-width: 1240px;
  margin: 0 auto;
  padding: 1.75rem 1.5rem 3rem;
  box-sizing: border-box;
}

/* Station : toute la hauteur disponible, sans défilement de page */
.page-frame.full-height {
  max-width: 1440px;
  height: 100%;
  padding: 1rem 1.5rem;
  display: flex;
  flex-direction: column;
}
.page-frame.full-height > * {
  flex: 1;
  min-height: 0;
}

@media (max-width: 860px) {
  .menu-toggle {
    display: inline-flex !important;
  }
  /* Navigation et déconnexion : dans le tiroir */
  .app-nav,
  .app-user {
    display: none;
  }
  .app-bar-inner {
    gap: 0.5rem;
    padding: 0 0.75rem;
  }
}

@media (max-width: 640px) {
  .page-frame {
    padding: 1rem 1rem 2.5rem;
  }
  .page-frame.full-height {
    padding: 0.5rem;
    height: auto;
    min-height: 100%;
  }
}
</style>
