import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// https://vite.dev/config/
export default defineConfig({
  plugins: [vue()],
  server: {
    host: '0.0.0.0',
    port: 5173,
    watch: {
      usePolling: true,
    },
    hmr: {
      host: 'localhost',
    },
    proxy: {
      // Rediriger toutes les requêtes commençant par /api vers le backend
      // Utilise 'fastapi' (nom du service Docker) au lieu de 'localhost'
      '/api': {
        target: 'http://fastapi:8000',
        changeOrigin: true,
      },
      // Rediriger UNIQUEMENT les routes API du chat (pas les routes frontend Vue)
      // Routes backend: /chat/attempts (pas /chat/:attemptId qui est une route Vue)
      '/chat/attempts': {
        target: 'http://fastapi:8000',
        changeOrigin: true,
      },
      // Rediriger les requêtes /auth vers le backend
      '/auth': {
        target: 'http://fastapi:8000',
        changeOrigin: true,
      },
      // Rediriger les requêtes /evaluation vers le backend
      '/evaluation': {
        target: 'http://fastapi:8000',
        changeOrigin: true,
      },
      // Rediriger les requêtes /admin vers le backend
      '/admin': {
        target: 'http://fastapi:8000',
        changeOrigin: true,
      },
      // Rediriger les requêtes /files (storage) vers le backend
      '/files': {
        target: 'http://fastapi:8000',
        changeOrigin: true,
      },
    },
  },
})
