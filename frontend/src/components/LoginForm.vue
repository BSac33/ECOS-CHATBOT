<script setup lang="ts">
import { ref } from 'vue';
import { useAuthStore } from '../stores/auth';
import InputText from 'primevue/inputtext';
import Password from 'primevue/password';
import Button from 'primevue/button';
import Message from 'primevue/message';
import { useRoute, useRouter } from 'vue-router';
import { apiService } from '../services/api';

const route = useRoute(); 
const router = useRouter()
const authStore = useAuthStore();

const username = ref('');
const password = ref('');
const errorMessage = ref('');

async function submit() {
  await apiService.login({username: username.value, password: password.value});
  await authStore.refreshSession();

  const redirect = route.query.redirect as string || undefined;
  router.replace(redirect || '/');
}

</script>

<template>
  <div class="login-container">
    <div class="login-card">
      <div class="login-header">
        <h1>ECOS Chatbot</h1>
        <p>Simulation de cas cliniques</p>
      </div>

      <form @submit.prevent="submit" class="login-form">
        <Message v-if="errorMessage" severity="error" :closable="false">
          {{ errorMessage }}
        </Message>

        <div class="field">
          <label for="username">Nom d'utilisateur</label>
          <InputText
            id="username"
            v-model="username"
            placeholder="Entrez votre nom d'utilisateur"
            class="w-full"
          />
        </div>

        <div class="field">
          <label for="password">Mot de passe</label>
          <Password
            id="password"
            v-model="password"
            placeholder="Entrez votre mot de passe"
            :feedback="false"
            toggleMask
            class="w-full"
          />
        </div>

        <Button
          type="submit"
          label="Se connecter"
          class="w-full"
          icon="pi pi-sign-in"
        />

        <div class="demo-accounts">
          <p class="demo-title">Comptes de démonstration :</p>
          <ul>
            <li><strong>Étudiant :</strong> etudiant_test / changeme123</li>
            <li><strong>Admin :</strong> admin / changeme123</li>
          </ul>
        </div>
      </form>
    </div>
  </div>
</template>

<style scoped>
.login-container {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  padding: 1rem;
}

.login-card {
  background: white;
  border-radius: 12px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.1);
  padding: 2.5rem;
  width: 100%;
  max-width: 420px;
}

.login-header {
  text-align: center;
  margin-bottom: 2rem;
}

.login-header h1 {
  color: #667eea;
  margin: 0 0 0.5rem 0;
  font-size: 2rem;
  font-weight: 700;
}

.login-header p {
  color: #6c757d;
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
  color: #495057;
  font-size: 0.95rem;
}

.w-full {
  width: 100%;
}

.demo-accounts {
  margin-top: 1rem;
  padding: 1rem;
  background: #f8f9fa;
  border-radius: 8px;
  font-size: 0.85rem;
}

.demo-title {
  margin: 0 0 0.5rem 0;
  font-weight: 600;
  color: #495057;
}

.demo-accounts ul {
  margin: 0;
  padding-left: 1.2rem;
  color: #6c757d;
}

.demo-accounts li {
  margin-bottom: 0.25rem;
}

:deep(.p-button) {
  padding: 0.75rem;
  font-weight: 600;
}

:deep(.p-inputtext),
:deep(.p-password input) {
  padding: 0.75rem;
}
</style>
