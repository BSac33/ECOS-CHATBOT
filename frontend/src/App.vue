<script setup lang="ts">
import { AIClient, type Message } from '@aivue/core';


const API_KEY = "AIzaSyB8zRvmHI8AuwSm0Ox-jDej7i4xk8KitkU";
const MODEL = import.meta.env.VITE_GEMINI_MODEL ?? "gemini-2.5-flash";

const aiClient = new AIClient({
  provider: "gemini",
  apiKey: "AIzaSyB8zRvmHI8AuwSm0Ox-jDej7i4xk8KitkU"
});

console.log("Using model:", MODEL);
console.log("API Key:", API_KEY ? "Provided" : "Not Provided");

const message: Message = {
  role: 'user',
  content: 'Hello, can you help me with Vue.js?'
};

const chat = await aiClient.chat([message]);
console.log("RAW CHAT:", chat);
console.log("RAW CHAT JSON:", JSON.stringify(chat, null, 2));

</script>

<template>
</template>

<style scoped>

</style>
