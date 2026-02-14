<template>

</template>

<script setup lang="ts">
defineProps<{
    case: {
        Name: string;
        Description: string;
        Items: { Id: string; Name: string; Link: string }[];
    };
}>();
</script>