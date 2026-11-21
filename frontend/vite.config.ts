/// <reference types="vitest/config" />
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// https://vite.dev/config/
export default defineConfig({
  plugins: [vue()],
  test: {
    environment: 'jsdom',
    include: ['src/**/*.test.ts'],
  },
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
      // API sous /api : préfixe retiré, comme nginx en production (/api/chat/attempts -> /chat/attempts)
      // Utilise 'fastapi' (nom du service Docker) au lieu de 'localhost'
      '/api': {
        target: 'http://fastapi:8000',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
      // Rediriger UNIQUEMENT les routes API du chat (pas les routes frontend Vue)
      // Routes backend: /chat/attempts (pas /chat/:attemptId qui est une route Vue)
      '/chat/attempts': {
        target: 'http://fastapi:8000',
        changeOrigin: true,
        ws: true, // mode vocal : WebSocket /chat/attempts/{id}/voice
      },
      // Rediriger les téléchargements de documents (examens affichés par l'examinateur)
      '/attachments': {
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
