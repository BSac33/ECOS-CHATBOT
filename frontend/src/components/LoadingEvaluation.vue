<template>
  <div class="loading-container">
    <div class="spinner"></div>
    <h2>Évaluation en cours...</h2>
    <p>Le LLM analyse votre performance. Cela peut prendre jusqu'à une minute.</p>
  </div>
</template>

<script setup lang="ts">
</script>

<style scoped>
.loading-container {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 60vh;
  gap: 1.5rem;
}

.spinner {
  width: 60px;
  height: 60px;
  border: 4px solid #f3f3f3;
  border-top: 4px solid #3498db;
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  0% { transform: rotate(0deg); }
  100% { transform: rotate(360deg); }
}

h2 {
  color: #333;
  margin: 0;
}

p {
  color: #666;
  margin: 0;
  text-align: center;
  max-width: 400px;
}
</style>
