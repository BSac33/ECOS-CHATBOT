<template>
<Dialog 
v-model:visible="visibleProxy" 
:header="props.header" 
modal>
    <slot />
</Dialog>
</template>

<script setup lang="ts">
import Dialog from 'primevue/dialog'
import { computed } from 'vue';

const props = defineProps<{
    visible: boolean;
    header: string;

}>();

const emit = defineEmits<{
    (e: 'update:visible', value: boolean): void;
}>();

const visibleProxy = computed({
    get: () => props.visible,
    set: (value: boolean) => emit('update:visible', value),
})

</script>

<style>
    .instructions {
    white-space: pre-wrap;   /* respecte les \n */
    line-height: 1.5;
    }
</style>