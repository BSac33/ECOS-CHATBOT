<template>
    <div class="evaluation-placeholder">
        <div class="content">
            <i class="pi pi-check-circle" style="font-size: 4rem; color: #28a745;"></i>
            <h1>Session terminée !</h1>
            <p>Votre tentative a été finalisée avec succès.</p>
            <p class="attempt-id">ID de tentative : {{ attemptId }}</p>
            
            <div class="actions">
                <Button 
                    label="Retour au Dashboard" 
                    icon="pi pi-home"
                    @click="$router.push('/')"
                />
            </div>
            
            <div class="info-box">
                <p><strong>Note :</strong> La page d'évaluation sera implémentée prochainement.</p>
                <p>Elle permettra de visualiser :</p>
                <ul>
                    <li>Votre score détaillé</li>
                    <li>Les points validés</li>
                    <li>Les recommandations</li>
                    <li>La correction complète</li>
                </ul>
            </div>
        </div>
    </div>
</template>

<script setup lang="ts">
import { defineProps } from 'vue';
import Button from 'primevue/button';

defineProps<{
    attemptId: string;
}>();
</script>

<style scoped>
.evaluation-placeholder {
    display: flex;
    justify-content: center;
    align-items: center;
    min-height: 100%;
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    border: 2rem solid white;
    padding: 1rem;
}

.content {
    background: white;
    border-radius: 16px;
    padding: 3rem;
    max-width: 600px;
    text-align: center;
    box-shadow: 0 10px 40px rgba(0, 0, 0, 0.2);
}

h1 {
    color: #333;
    margin: 1rem 0;
    font-size: 2rem;
}

p {
    color: #666;
    line-height: 1.6;
}

.attempt-id {
    font-family: 'Courier New', monospace;
    background: #f8f9fa;
    padding: 0.5rem 1rem;
    border-radius: 8px;
    margin: 1.5rem 0;
    font-size: 0.9rem;
    color: #495057;
}

.actions {
    margin: 2rem 0;
}

.info-box {
    background: #e7f3ff;
    border-left: 4px solid #667eea;
    padding: 1.5rem;
    border-radius: 8px;
    text-align: left;
    margin-top: 2rem;
}

.info-box p {
    margin: 0.5rem 0;
}

.info-box ul {
    margin: 0.5rem 0;
    padding-left: 1.5rem;
    color: #666;
}

.info-box li {
    margin: 0.3rem 0;
}
</style>
