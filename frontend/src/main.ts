import { createApp } from 'vue'
import App from './App.vue'
import PrimeVue from 'primevue/config'
import Aura from '@primeuix/themes/aura'
import { createPinia } from 'pinia'
import { createAppRouter } from './router'
import './style.css'

import 'primeicons/primeicons.css'

const app = createApp(App)

const pinia = createPinia()
app.use(pinia)

const router = createAppRouter(pinia)
app.use(router)
app.use(PrimeVue, { 
  theme: { 
    preset: Aura,
    options: {
      darkModeSelector: 'none' // Désactive le mode sombre automatique
    }
  } 
})

app.mount('#app')