import { createRouter, createWebHistory } from 'vue-router'
import { routes } from '../routes'
import { useAuthStore } from '../stores/auth'
import type { Pinia } from 'pinia'
import { isTeacher } from '../authoring/api'

export function createAppRouter(pinia: Pinia) {
  const router = createRouter({
    history: createWebHistory(),
    routes,
  })

  router.beforeEach(async (to) => {
    const auth = useAuthStore(pinia)

    // ✅ hydrate une seule fois (au 1er passage)
    if (!auth.isHydrated) {
      await auth.hydrate()
    }

    // ✅ si route protégée et non loggé → login + redirect vers la page voulue
    if (to.meta.requiresAuth && !auth.isAuthenticated) {
      return { name: 'login', query: { redirect: to.fullPath } }
    }

    // Atelier réservé aux enseignants et administrateurs
    if (to.meta.requiresTeacher && !isTeacher(auth.user)) {
      return { path: '/' }
    }

    // ✅ si déjà loggé et va sur /login → redirect vers la page demandée ou /
    if (to.name === 'login' && auth.isAuthenticated) {
      return { path: (to.query.redirect as string) || '/' }
    }

    return true
  })

  return router
}