
<template>
    <div class="card flex justify-center" style="display:flex; min-height:0; align-items:center; gap:1rem; justify-content:flex-end; ">
        <Textarea v-model="value" auto-resize  rows="2"fluid />
        <Button icon="pi pi-send" style="padding: 1rem; padding-left: 1rem; padding-right: 1rem;" />
    </div>
</template>

<script setup>
import { ref } from 'vue';
import Textarea from 'primevue/textarea';
import Button from 'primevue/button';

const value = ref('');
</script>
