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
    <!-- Bouton flottant en position fixe à gauche -->
    <div class="floating-menu-button" :class="{ 'menu-open': visible }">
      <Drawer v-model:visible="visible" header="Menu principal">
        <p><RouterLink @click="visible = false" to="/">Dashboard</RouterLink></p>
        <p><RouterLink @click="visible = false" to="/login">Login</RouterLink></p>
      </Drawer>

      <Button icon="pi pi-bars" @click="visible = true" rounded />
    </div>

    <!-- Vue principale sans décalage -->
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

/* Bouton flottant fixe en haut à gauche */
.floating-menu-button {
  position: fixed;
  top: 1rem;
  left: 1rem;
  z-index: 1000; /* Au-dessus du contenu */
  transition: opacity 0.3s ease;
}

/* Masquer le bouton quand le menu est ouvert */
.floating-menu-button.menu-open {
  opacity: 0;
  pointer-events: none;
}

.main-view {
  flex: 1;
  min-height: 0;  /* 🔥 super important */
  padding-left: 4rem;
  padding-right: 4rem;
  overflow: hidden;
}
</style>