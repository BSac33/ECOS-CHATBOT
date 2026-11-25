import { createApp } from 'vue'
import { createPinia } from 'pinia'
import PrimeVue from 'primevue/config'
import ToastService from 'primevue/toastservice'
import { EcosTheme } from './theme'
import App from './App.vue'
import { createAppRouter } from './router'
import { fr } from './locale-fr'
import 'primeicons/primeicons.css'
import './style.css'

const app = createApp(App)

const pinia = createPinia()
app.use(pinia)

app.use(createAppRouter(pinia))
app.use(PrimeVue, {
  locale: fr,
  theme: {
    preset: EcosTheme,
    options: {
      darkModeSelector: 'none', // pas de mode sombre automatique
    },
  },
})
app.use(ToastService)

app.mount('#app')
