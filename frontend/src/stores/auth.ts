// stores/auth.ts
import { defineStore } from 'pinia'
import { apiService } from '../services/api' // doit faire credentials: 'include'

export const useAuthStore = defineStore('auth', {
  state: () => ({
    user: null as any | null,
    isHydrated: false,
    isAuthenticated: false
  }),
  getters: {
    isAuthenticated: (s) => !!s.user,
  },
  actions: {
    async hydrate() {
      if (this.isHydrated) return
      this.isHydrated = true
      await this.refreshSession()
    },

    async refreshSession() {
      try {
        this.user = await apiService.getCurrentUser() // /api/users/me
      } catch (e: any) {
        this.user = null
        // si tu veux être strict: uniquement si 401
      }
    },

    async logout() {
      try {
        await apiService.logout?.() // si tu as /auth/logout
      } finally {
        this.user = null
      }
    },
  },
})