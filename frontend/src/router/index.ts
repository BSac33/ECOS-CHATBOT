import { createRouter, createWebHistory, type RouterHistory } from 'vue-router'
import type { Pinia } from 'pinia'
import { routes } from '../routes'
import { useAuthStore } from '../stores/auth'
import { isTeacher } from '../authoring/api'
import { setUnauthorizedHandler } from '../services/http'

export const APP_TITLE = 'ECOS – Entraînement'

/** Retour après connexion : seulement un chemin interne (pas de redirection ouverte). */
export function safeRedirect(value: unknown): string {
  const target = Array.isArray(value) ? value[0] : value
  if (typeof target !== 'string' || !target.startsWith('/') || target.startsWith('//') || target.startsWith('/\\')) {
    return '/'
  }
  return target.startsWith('/login') ? '/' : target
}

export function createAppRouter(pinia: Pinia, history: RouterHistory = createWebHistory()) {
  // Le défilement se fait dans .main-view (App.vue), qui revient en haut à chaque page
  const router = createRouter({ history, routes })

  router.beforeEach(async (to) => {
    const auth = useAuthStore(pinia)

    // Vérifie la session une seule fois (au premier passage)
    if (!auth.isHydrated) {
      await auth.hydrate()
    }

    // Page protégée sans session : connexion, puis retour à la page demandée
    if (to.meta.requiresAuth && !auth.isAuthenticated) {
      return { name: 'login', query: { redirect: to.fullPath } }
    }

    // Atelier réservé aux enseignants et administrateurs
    if (to.meta.requiresTeacher && !isTeacher(auth.user)) {
      return { path: '/' }
    }

    // Déjà connecté : la page de connexion renvoie vers la page demandée
    if (to.name === 'login' && auth.isAuthenticated) {
      return { path: safeRedirect(to.query.redirect) }
    }

    return true
  })

  // Titre de l'onglet par page (lu en premier par les lecteurs d'écran)
  router.afterEach((to) => {
    document.title = to.meta.title ? `${to.meta.title} – ${APP_TITLE}` : APP_TITLE
  })

  // Session expirée (401 sur un appel de l'API) : on oublie l'utilisateur et on passe
  // par la connexion, qui ramène ensuite sur la page en cours.
  setUnauthorizedHandler(() => {
    useAuthStore(pinia).clear()
    const current = router.currentRoute.value
    if (current.name === 'login') return
    void router.replace({ name: 'login', query: { redirect: current.fullPath } })
  })

  return router
}
