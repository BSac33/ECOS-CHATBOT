<script setup lang="ts">
  import { onMounted, ref } from 'vue';
  import { useAuthStore } from './stores/auth';
  import type { CaseInstructions, ClinicalCase } from './services/api';
  import { stationType } from './services/api';
  import { apiService } from './services/api';
  import Card from 'primevue/card';
  import Button from 'primevue/button';
  import InstructionPopup from './components/InstructionPopup.vue';
  import { useRouter } from 'vue-router';


  const authStore = useAuthStore();
  const errorMessage = ref<string | null>(null);
  const caseList = ref<Array<ClinicalCase>>([]);

  const router = useRouter();

  const isVisible = ref(false);
  const popupContent = ref<CaseInstructions| null>(null);

  onMounted(async() => {
    try {
      caseList.value = await apiService.getClinicalCases();
    } catch (error) {
      errorMessage.value = 'Erreur lors du chargement des cas cliniques.';
    }
  })

  async function populatePopup(caseId: number)
  {
    popupContent.value = await apiService.getCaseInstructions(caseId);
  }

  async function createAttempt(caseId: number) {
    try {
      // Vérifier d'abord s'il existe un attempt actif
      const activeAttempt = await apiService.getActiveAttempt(caseId);
      
      if (activeAttempt) {
        console.log('✅ Attempt actif trouvé, redirection...');
        router.push(`/chat/${activeAttempt.id}`);
        return;
      }
      
      // Sinon, créer un nouvel attempt
      console.log('🆕 Création d\'un nouvel attempt...');
      const attempt = await apiService.createAttempt(caseId);
      router.push(`/chat/${attempt.id}`);

    } catch (error) {
      console.error('Erreur lors de la création de la tentative :', error);
      throw error;
    }
  }

</script>

<template>
  <div v-if="authStore.isAuthenticated">
    <h1>Dashboard</h1>
    <p>Welcome, {{ authStore.user.username }}!</p>
    <div id="instruction-container">
    <InstructionPopup v-if="popupContent" v-model:visible="isVisible" style="width:50rem; padding:1rem; background-color:#f5f5f5;" 
      :header="popupContent.title || ''">
      <div class="instructions"> {{ popupContent.student_instructions }}</div>
      <div class="actions" style="display:flex; justify-content:space-between; padding-top:2rem;">
        <Button label="Fermer" @click="isVisible = false" class="p-button-text"/>
        <Button 
          label="Commencer l'examen" 
          icon="pi pi-play" 
          @click="async() => {
            await createAttempt(popupContent.case_id)
            isVisible = false
            }"/>
      </div>
    </InstructionPopup>
    <p v-else>No popup found</p>

    </div>
    <div id="case-container">
<Card
  v-for="caseItem in caseList"
  :key="caseItem.id"
  class="case-card"
>
  <template #title>{{ caseItem.title }}</template>

  <template #subtitle>
    <p>{{ stationType[caseItem.station_type] }}</p>
    <p>{{ caseItem.disciplines.join(', ') }}</p>
  </template>

  <template #footer>
    <div class="card-footer">
      <Button 
        label="Voir plus" 
        @click="async () => { 
          await populatePopup(caseItem.id);
          isVisible = true; }"
        class="p-button-text"/>
    </div>
  </template>
</Card>
    </div>
  </div>
  <div v-else>
    <p>{{ errorMessage }}</p>
  </div>

</template>

<style>
  #case-container {
    display: flex;
    flex-wrap: wrap;
    justify-content: center;
    gap: 1rem;
    margin-top: 2rem;
    padding: 1rem;
    background-color: lightgray;
  }

  .case-card {
  width: 25rem;
  height: 15rem;
  display: flex;
  flex-direction: column;
}

.case-card .p-card-body {
  display: flex;
  flex-direction: column;
  flex: 1;
}

.case-card .p-card-footer {
  margin-top: auto;
}

.card-footer {
  display: flex;
  justify-content: flex-end;
}
</style>