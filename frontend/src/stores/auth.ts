// Session de l'utilisateur (cookie JWT HttpOnly : seul l'utilisateur courant est gardé ici)
import { defineStore } from 'pinia'
import { apiService } from '../services/api'
import type { User } from '../types'

interface AuthState {
  user: User | null
  isHydrated: boolean
}

export const useAuthStore = defineStore('auth', {
  state: (): AuthState => ({
    user: null,
    isHydrated: false,
  }),
  getters: {
    isAuthenticated: (state): boolean => state.user !== null,
    /** Nom affiché : nom complet, sinon identifiant */
    displayName: (state): string => state.user?.full_name || state.user?.username || '',
  },
  actions: {
    async hydrate(): Promise<void> {
      if (this.isHydrated) return
      this.isHydrated = true
      await this.refreshSession()
    },

    async refreshSession(): Promise<void> {
      try {
        this.user = await apiService.getCurrentUser()
      } catch {
        // 401 (non connecté) ou serveur injoignable : pas de session
        this.user = null
      }
    },

    /** Session expirée ou compte supprimé : on oublie l'utilisateur sans appeler le serveur. */
    clear(): void {
      this.user = null
    },

    /** Déconnexion : le serveur efface le cookie ; la session locale est vidée dans tous les cas. */
    async logout(): Promise<void> {
      try {
        await apiService.logout()
      } catch {
        // serveur injoignable : on déconnecte quand même côté navigateur
      } finally {
        this.clear()
      }
    },
  },
})
