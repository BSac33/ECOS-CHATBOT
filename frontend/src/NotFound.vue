<script setup lang="ts">
import { RouterLink } from 'vue-router'
</script>

<template>
  <div class="not-found">
    <h1>Page introuvable</h1>
    <p>L'adresse demandée n'existe pas ou n'est plus disponible.</p>
    <p><RouterLink :to="{ name: 'dashboard' }">Retour aux stations</RouterLink></p>
  </div>
</template>

<style scoped>
.not-found {
  padding: 2rem 0;
  max-width: 40rem;
}

.not-found p {
  color: #374151;
}
</style>
