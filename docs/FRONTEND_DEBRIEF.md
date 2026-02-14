# Frontend - Page Debrief

## 📋 Vue d'ensemble

La page **Debrief** (`frontend/src/Debrief.vue`) affiche les résultats détaillés de l'évaluation d'une tentative ECOS finalisée. Elle permet à l'étudiant de consulter son score, les points obtenus par critère, et les justifications de l'évaluateur.

## 🏗️ Architecture

### Fichiers concernés

```
frontend/src/
├── Debrief.vue                      # Page principale de résultats
└── components/
    └── EvaluationItem.vue           # Composant item d'évaluation
```

## 📊 Structure des Données

### Flux de données API → Frontend

```
Backend LLM Response
        ↓
{
  evaluation: {
    items: [{
      item_id: "item_1"           → edn_code
      criterion: "..."            → item_name
      points_awarded: 1.0         → points_obtained
      points_possible: 1.0        → points_possible
      is_validated: true          → (utilisé pour validation)
      justification: "..."        → justification
    }],
    total_score: 15.5             → total_score
    total_possible: 20.0          → points_possible
    percentage: 77.5              → (calculé)
    general_feedback: "..."       → overall_feedback
  },
  cached: false
}
        ↓
Frontend Display
```

### Interfaces TypeScript

#### Données brutes de l'API

```typescript
interface EvaluationItemRaw {
  item_id: string           // Code EDN de l'item
  criterion: string         // Nom du critère évalué
  points_awarded: number    // Points obtenus
  points_possible: number   // Points maximum possible
  is_validated: boolean     // Item validé (≥50%) ou non
  justification: string     // Justification de l'évaluateur
}

interface EvaluationRaw {
  items: EvaluationItemRaw[]
  total_score: number       // Score total obtenu
  total_possible: number    // Score maximum possible
  percentage: number        // Pourcentage de réussite
  general_feedback: string  // Feedback global
}

interface EvaluationResponse {
  evaluation: EvaluationRaw
  cached?: boolean          // Indique si l'évaluation provient du cache
}
```

#### Données mappées pour l'affichage

```typescript
interface EvaluationItemData {
  edn_code: string          // Code EDN (ex: cardio_001)
  item_name: string         // Libellé du critère
  points_obtained: number   // Points obtenus
  points_possible: number   // Points maximum
  justification: string     // Justification détaillée
}

interface EvaluationData {
  total_score: number
  points_possible: number
  overall_feedback: string
  items: EvaluationItemData[]
}

interface CaseInfo {
  title: string             // Titre du cas clinique
  edn_codes: string[]       // Liste des codes EDN pour ressources
}
```

## 🔄 Flux de Chargement des Données

### Séquence d'appels API

```typescript
async function loadEvaluationData() {
  try {
    // 1️⃣ Récupération de l'évaluation
    const evaluationResponse = await apiService.getAttemptEvaluation(attemptId)
    
    // 2️⃣ Mapping des données
    const evalData = evaluationResponse.evaluation
    evaluation.value = {
      total_score: evalData.total_score,
      points_possible: evalData.total_possible,
      overall_feedback: evalData.general_feedback,
      items: evalData.items.map(item => ({
        edn_code: item.item_id,
        item_name: item.criterion,
        points_obtained: item.points_awarded,
        points_possible: item.points_possible,
        justification: item.justification
      }))
    }
    
    // 3️⃣ Récupération du transcript pour obtenir case_id
    const transcriptResponse = await apiService.getAttemptTranscript(attemptId)
    const caseId = transcriptResponse.case_id
    
    // 4️⃣ Récupération des détails du cas clinique
    const caseResponse = await apiService.getClinicalCase(caseId)
    caseInfo.value = {
      title: caseResponse.title,
      edn_codes: caseResponse.edn_codes || []
    }
  } catch (error) {
    console.error('Erreur lors du chargement:', error)
  } finally {
    isLoading.value = false
  }
}
```

### Endpoints utilisés

| Endpoint | Méthode | Paramètre | Retour |
|----------|---------|-----------|--------|
| `/evaluation/attempts/{id}/evaluate` | POST | attempt_id | EvaluationResponse |
| `/evaluation/attempts/{id}/transcript` | GET | attempt_id | { case_id, transcript[] } |
| `/api/cases/{id}` | GET | case_id | { title, edn_codes[] } |

## 🎨 Interface Utilisateur

### Structure de la page

```
┌─────────────────────────────────────┐
│  📄 Titre du Cas Clinique           │  ← Header (fixe)
├─────────────────────────────────────┤
│  ┌───────────────────────────────┐  │
│  │ 🎯 Score Global               │  │  ← Carte score (fixe)
│  │ 15.5 / 20                     │  │
│  │ 77.5%                         │  │
│  └───────────────────────────────┘  │
├─────────────────────────────────────┤
│  ╔═════════════════════════════╗  │
│  ║ Zone Scrollable             ║  │  ← Contenu scrollable
│  ║                             ║  │     max-height: calc(100vh - 350px)
│  ║ ┌─────────────────────────┐ ║  │
│  ║ │ ✓ cardio_001            │ ║  │     Items d'évaluation
│  ║ │ 1.0 / 1.0               │ ║  │     (EvaluationItem × N)
│  ║ │ Justification...        │ ║  │
│  ║ └─────────────────────────┘ ║  │
│  ║                             ║  │
│  ║ ┌─────────────────────────┐ ║  │
│  ║ │ ✗ cardio_002            │ ║  │
│  ║ │ 0.5 / 1.0               │ ║  │
│  ║ │ Justification...        │ ║  │
│  ║ └─────────────────────────┘ ║  │
│  ║                             ║  │
│  ║ ┌─────────────────────────┐ ║  │
│  ║ │ 💬 Retour Global        │ ║  │     Feedback global
│  ║ │ Bonne performance...    │ ║  │
│  ║ └─────────────────────────┘ ║  │
│  ║                             ║  │
│  ║ ┌─────────────────────────┐ ║  │
│  ║ │ 🔗 Pour Approfondir     │ ║  │     Ressources EDN
│  ║ │ • cardio_001            │ ║  │
│  ║ │ • cardio_002            │ ║  │
│  ║ └─────────────────────────┘ ║  │
│  ╚═════════════════════════════╝  │
└─────────────────────────────────────┘
```

### Composant EvaluationItem

#### Props
```typescript
interface Props {
  item: {
    edn_code: string
    item_name: string
    points_obtained: number
    points_possible: number
    justification: string
  }
}
```

#### Logique de validation

```typescript
const isValidated = computed(() => {
  const percentage = (props.item.points_obtained / props.item.points_possible) * 100
  return percentage >= 50
})
```

#### Rendu visuel

```html
<div class="evaluation-item" :class="{ validated: isValidated }">
  <!-- Icône de validation -->
  <div class="status-icon">
    <svg v-if="isValidated"><!-- Checkmark vert --></svg>
    <svg v-else><!-- Croix rouge --></svg>
  </div>
  
  <!-- Informations -->
  <div class="item-content">
    <div class="item-header">
      <span class="edn-code">{{ item.edn_code }}</span>
      <span class="score">{{ item.points_obtained }}/{{ item.points_possible }}</span>
    </div>
    <h4 class="item-title">{{ item.item_name }}</h4>
    <p class="justification">{{ item.justification }}</p>
  </div>
</div>
```

## 🎨 Styling et UX

### Palette de couleurs

```css
/* Score global */
--gradient-primary: linear-gradient(135deg, #667eea 0%, #764ba2 100%);

/* Validation */
--color-success: #10b981;  /* Vert pour items validés */
--color-error: #ef4444;    /* Rouge pour items non validés */

/* Feedback global */
--color-info: #667eea;     /* Bleu pour feedback */

/* Ressources */
--color-resources: #10b981; /* Vert pour liens EDN */
```

### Scrollbar personnalisée

```css
.scrollable-content::-webkit-scrollbar {
  width: 8px;
}

.scrollable-content::-webkit-scrollbar-track {
  background: #f1f5f9;
  border-radius: 4px;
}

.scrollable-content::-webkit-scrollbar-thumb {
  background: #cbd5e1;
  border-radius: 4px;
}

.scrollable-content::-webkit-scrollbar-thumb:hover {
  background: #94a3b8;
}
```

### Responsive

- **Desktop** : Affichage optimal avec sidebar
- **Tablet** : Layout adapté, scrolling fluide
- **Mobile** : Score réduit, items empilés

## 🔧 Computed Properties

### Calcul du pourcentage

```typescript
const scorePercentage = computed(() => {
  if (!evaluation.value) return 0
  return Math.round(
    (evaluation.value.total_score / evaluation.value.points_possible) * 100
  )
})
```

### Formatage du score

```typescript
const scoreDisplay = computed(() => {
  if (!evaluation.value) return '- / -'
  return `${evaluation.value.total_score} / ${evaluation.value.points_possible}`
})
```

## 🐛 Gestion des Erreurs

### États de chargement

```typescript
const isLoading = ref(true)
const error = ref<string | null>(null)

// Affichage conditionnel
<LoadingEvaluation v-if="isLoading" />
<ErrorMessage v-else-if="error" :message="error" />
<div v-else class="debrief-container">...</div>
```

### Cas limites

| Situation | Comportement |
|-----------|--------------|
| Évaluation vide | Affiche message "Aucun résultat disponible" |
| Items manquants | Affiche liste vide avec message informatif |
| EDN codes absents | Masque la section "Pour Approfondir" (v-if) |
| API timeout | Affiche erreur avec bouton "Réessayer" |

## 🚀 Optimisations

### Chargement paresseux

```typescript
// Les composants lourds sont lazy-loaded
const EvaluationItem = defineAsyncComponent(() => 
  import('./components/EvaluationItem.vue')
)
```

### Cache API

```typescript
// L'évaluation est cachée côté backend
// Appels multiples = réponse instantanée
const response = await apiService.getAttemptEvaluation(attemptId)
if (response.cached) {
  console.log('✅ Évaluation servie depuis le cache')
}
```

## 📱 Navigation

### Intégration dans le flux utilisateur

```
Simulation → Finalisation → [Debrief]
    ↑                          ↓
    └──────── Réessayer ←──────┘
```

### Route Vue Router

```typescript
{
  path: '/debrief/:attemptId',
  name: 'Debrief',
  component: Debrief,
  meta: { requiresAuth: true }
}
```

### Accès à la page

```typescript
// Depuis ChatView après finalisation
router.push({ 
  name: 'Debrief', 
  params: { attemptId: attempt.id } 
})
```

## 🧪 Tests Recommandés

### Scénarios de test

1. **Chargement nominal** : Vérifier l'affichage avec données complètes
2. **Cache hit** : Vérifier que `cached: true` n'affecte pas l'affichage
3. **Évaluation partielle** : Items avec points partiels (0.5/1.0)
4. **Longue justification** : Texte débordant dans EvaluationItem
5. **Scroll fluide** : Tester avec 14+ items d'évaluation
6. **EDN codes vides** : Section "Pour Approfondir" masquée
7. **Erreur API** : Affichage message d'erreur

### Tests unitaires

```typescript
describe('Debrief.vue', () => {
  it('mappe correctement les données LLM vers le frontend', () => {
    const raw = {
      evaluation: {
        items: [{ item_id: 'test', criterion: 'Test' }],
        total_score: 10,
        total_possible: 20,
        general_feedback: 'Bien'
      }
    }
    
    const mapped = mapEvaluationData(raw)
    expect(mapped.items[0].edn_code).toBe('test')
    expect(mapped.items[0].item_name).toBe('Test')
  })
})
```

## 📝 Améliorations Futures

### Fonctionnalités envisagées

- [ ] Export PDF du debrief complet
- [ ] Comparaison entre plusieurs tentatives
- [ ] Graphique de progression (radar chart)
- [ ] Annotations manuelles de l'étudiant
- [ ] Partage sécurisé avec enseignants
- [ ] Mode impression optimisé
- [ ] Traduction i18n (FR/EN)
- [ ] Animations d'apparition des items
- [ ] Filtrage par validation (montrer uniquement les erreurs)
- [ ] Liens directs vers ressources EDN externes

---

**Dernière mise à jour** : Février 2026  
**Auteur** : Benjamin Sacristan
