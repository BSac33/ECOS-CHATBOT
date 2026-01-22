<template>
  <div class="countdown-overlay">
    <div class="countdown-circle">
      <div class="countdown-number" :key="count">
        {{ count }}
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue';

const emit = defineEmits<{
  complete: [];
}>();

const count = ref(3);

onMounted(() => {
  const interval = setInterval(() => {
    count.value--;
    
    if (count.value === 0) {
      clearInterval(interval);
      setTimeout(() => {
        emit('complete');
      }, 1000); // Attendre 1 seconde après "GO!" avant de commencer
    }
  }, 1000);
});
</script>

<style scoped>
.countdown-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.8);
  backdrop-filter: blur(8px);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 2000;
  animation: fadeIn 0.3s ease;
}

@keyframes fadeIn {
  from {
    opacity: 0;
  }
  to {
    opacity: 1;
  }
}

.countdown-circle {
  width: 200px;
  height: 200px;
  border-radius: 50%;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 20px 60px rgba(102, 126, 234, 0.5);
  animation: pulse 1s ease infinite;
}

@keyframes pulse {
  0%, 100% {
    transform: scale(1);
  }
  50% {
    transform: scale(1.1);
  }
}

.countdown-number {
  font-size: 6rem;
  font-weight: bold;
  color: white;
  animation: numberPop 0.5s ease;
}

@keyframes numberPop {
  0% {
    transform: scale(0.5);
    opacity: 0;
  }
  50% {
    transform: scale(1.2);
  }
  100% {
    transform: scale(1);
    opacity: 1;
  }
}

@media (max-width: 768px) {
  .countdown-circle {
    width: 150px;
    height: 150px;
  }

  .countdown-number {
    font-size: 4rem;
  }
}
</style>
