<template>
  <div class="loading-container" role="status" aria-live="polite">
    <div class="spinner" aria-hidden="true"></div>
    <h1>Correction en cours…</h1>
    <p>L'analyse de votre passage peut prendre jusqu'à quelques minutes. Vous pouvez rester sur cette page.</p>
  </div>
</template>

<style scoped>
.loading-container {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 60vh;
  gap: 1.5rem;
  text-align: center;
}

.spinner {
  width: 60px;
  height: 60px;
  border: 4px solid #e5e7eb;
  border-top: 4px solid #1d4ed8;
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  0% { transform: rotate(0deg); }
  100% { transform: rotate(360deg); }
}

/* Mouvement réduit : la roue ralentit fortement au lieu de tourner vite */
@media (prefers-reduced-motion: reduce) {
  .spinner {
    animation: none;
    border-top-color: #93c5fd;
  }
}

h1 {
  color: #1f2937;
  font-size: 1.5rem;
  margin: 0;
}

p {
  color: #4b5563;
  margin: 0;
  max-width: 400px;
}
</style>
