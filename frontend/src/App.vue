<script setup lang="ts">
import { RouterLink, RouterView } from 'vue-router';
import { Drawer } from 'primevue';
import Button from 'primevue/button';
import { ref } from 'vue';
import 'primeicons/primeicons.css';

const visible = ref(false);
</script>

<template>
  <div class="app-shell">
    <div class="topbar">
      <Drawer v-model:visible="visible" header="Menu principal">
        <p><RouterLink @click="visible = false" to="/">Dashboard</RouterLink></p>
        <p><RouterLink @click="visible = false" to="/login">Login</RouterLink></p>
      </Drawer>

      <Button icon="pi pi-arrow-right" @click="visible = true" />
    </div>

    <div class="main-view">
      <RouterView />
    </div>
  </div>
</template>

<style>

.app-shell {
  height: 100%;
  display: flex;
  flex-direction: column;
  min-height: 0; /* important pour le scroll interne */
}

.topbar {
  flex: 0 0 auto;
  padding: 1rem;
  border-bottom: 1px solid #eee;
}

.main-view {
  flex: 1;
  min-height: 0;  /* 🔥 super important */
  padding: 4rem;
  overflow:hidden
}
</style>