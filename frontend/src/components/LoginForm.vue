<script setup lang="ts">
import { ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import InputText from 'primevue/inputtext';
import Password from 'primevue/password';
import Button from 'primevue/button';
import Message from 'primevue/message';
import { useAuthStore } from '../stores/auth';
import { apiService } from '../services/api';
import { ApiError } from '../services/http';
import { safeRedirect } from '../router';

const route = useRoute();
const router = useRouter();
const authStore = useAuthStore();

const username = ref('');
const password = ref('');
const errorMessage = ref('');
const submitting = ref(false);

const FALLBACK = 'Connexion impossible, réessayez.';

async function submit() {
  if (submitting.value) return;
  errorMessage.value = '';
  if (!username.value.trim() || !password.value) {
    errorMessage.value = "Saisissez votre nom d'utilisateur et votre mot de passe.";
    return;
  }
  submitting.value = true;
  try {
    await apiService.login({ username: username.value.trim(), password: password.value });
    await authStore.refreshSession();
    if (!authStore.isAuthenticated) {
      errorMessage.value = FALLBACK;
      return;
    }
    password.value = '';
    await router.replace(safeRedirect(route.query.redirect));
  } catch (error) {
    // Message de l'API (en français) s'il y en a un, sinon message générique
    errorMessage.value = error instanceof ApiError && typeof error.detail === 'string' && error.detail.trim()
      ? error.detail
      : FALLBACK;
  } finally {
    submitting.value = false;
  }
}
</script>

<template>
  <div class="login-container">
    <div class="login-card">
      <div class="login-header">
        <h1>ECOS – Entraînement</h1>
        <p>Simulation de stations cliniques</p>
      </div>

      <form class="login-form" novalidate @submit.prevent="submit">
        <!-- Message PrimeVue : role="alert", annoncé dès son apparition -->
        <Message v-if="errorMessage" severity="error" :closable="false">
          {{ errorMessage }}
        </Message>

        <div class="field">
          <label for="username">Nom d'utilisateur</label>
          <InputText
            id="username"
            v-model="username"
            name="username"
            autocomplete="username"
            autocapitalize="none"
            spellcheck="false"
            required
            :invalid="!!errorMessage && !username.trim()"
            class="w-full"
          />
        </div>

        <div class="field">
          <label for="password">Mot de passe</label>
          <Password
            v-model="password"
            input-id="password"
            :input-props="{ name: 'password', autocomplete: 'current-password', required: true }"
            :feedback="false"
            toggle-mask
            :invalid="!!errorMessage && !password"
            class="w-full"
            input-class="w-full"
          />
        </div>

        <Button
          type="submit"
          label="Se connecter"
          class="w-full"
          icon="pi pi-sign-in"
          :loading="submitting"
        />
      </form>

      <p class="ai-notice login-ai">
        <i class="pi pi-sparkles" aria-hidden="true"></i>
        <span>
          Cette plateforme utilise l'intelligence artificielle pour simuler les patients et proposer une correction.
        </span>
      </p>
    </div>
  </div>
</template>

<style scoped>
.login-container {
  min-height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #4338ca 0%, #6d28d9 100%);
  padding: 1rem;
  box-sizing: border-box;
}

.login-card {
  background: white;
  border-radius: 12px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.1);
  padding: 2.5rem;
  width: 100%;
  max-width: 420px;
  box-sizing: border-box;
}

.login-header {
  text-align: center;
  margin-bottom: 2rem;
}

.login-header h1 {
  color: #3730a3;
  margin: 0 0 0.5rem 0;
  font-size: 1.75rem;
  font-weight: 700;
}

.login-header p {
  color: #4b5563;
  margin: 0;
  font-size: 0.95rem;
}

.login-form {
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
}

.field {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.field label {
  font-weight: 600;
  color: #374151;
  font-size: 0.95rem;
}

.w-full {
  width: 100%;
}

.login-ai {
  margin: 1.5rem 0 0;
  align-items: flex-start;
  line-height: 1.4;
}

.login-ai .pi {
  margin-top: 0.2rem;
}

:deep(.p-button) {
  padding: 0.75rem;
  font-weight: 600;
}

:deep(.p-inputtext),
:deep(.p-password input) {
  padding: 0.75rem;
}

@media (max-width: 480px) {
  .login-card {
    padding: 1.5rem;
  }
}
</style>
