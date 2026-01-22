<template>
    <div style="display:flex; min-height:0;  gap:1rem; flex-direction: column; padding:1rem; height:100%">
        <div style="display: flex; min-height: 0; flex:1 ; overflow-y: auto; padding: 1rem;">
            <p>Hello</p>
        </div>
    <Textbox style="padding:1rem;"/>

    </div>


</template>

<script setup lang="ts">
    import { useRoute } from 'vue-router';
    import Textbox from './components/Textbox.vue';

    const route = useRoute();
    const attemptId = route.params.attemptId as string;

</script>