# Système d'Évaluation ECOS

## Principe Fondamental

**Dans un ECOS réel, l'évaluateur ne parle JAMAIS avec l'étudiant pendant l'examen.**

L'évaluateur observe silencieusement la performance et remplit une grille d'évaluation. Cette application respecte ce principe :

- ✅ **Chat en temps réel** : Uniquement pour les stations avec **impersonation patient**
- ✅ **Évaluation** : Se fait **après la fin** en analysant le transcript complet
- ❌ **Pas de mode "évaluateur en chat"** : L'évaluateur ne guide pas l'étudiant pendant l'examen

## Architecture du Système

### 1. Types de Stations

#### Stations AVEC conversation (chat en temps réel)
- `patient_interview` : Interrogatoire patient
- `diagnosis_announcement` : Annonce de diagnostic
- `mixed` : Station mixte (ex: interrogatoire puis examen)

**Fonctionnement** :
- L'étudiant dialogue avec le LLM qui joue le rôle du patient
- Le transcript est enregistré dans la base de données
- À la fin, appel à `/evaluation/attempts/{id}/evaluate` pour l'évaluation

#### Stations SANS conversation (réponse unique)
- `exam_analysis` : Analyse d'examens (radio, ECG, labo)
- `procedure` : Démonstration de geste technique

**Fonctionnement** :
- L'étudiant soumet sa réponse complète en un seul message
- Pas de dialogue en temps réel avec le LLM
- L'appel au chat retourne une erreur 400 explicite
- L'étudiant finalise puis demande l'évaluation

## Flux de Travail

### Pour Stations avec Patient

```
1. POST /chat/attempts
   → Créer une tentative
   ↓
2. POST /chat/attempts/{id}/chat (× N fois)
   → Conversation étudiant ↔ patient (LLM)
   ↓
3. POST /chat/attempts/{id}/finalize
   → Marquer la tentative comme terminée
   ↓
4. POST /evaluation/attempts/{id}/evaluate
   → Analyse du transcript et évaluation
   ↓
5. Résultat JSON structuré
```

### Pour Stations sans Patient

```
1. POST /chat/attempts
   → Créer une tentative
   ↓
2. POST /chat/attempts/{id}/chat
   ⚠️ ERREUR 400: "Cette station ne supporte pas le chat en temps réel"
   
   Alternative:
   → L'étudiant écrit sa réponse complète dans un formulaire
   → Enregistrement direct en base via un endpoint dédié (TODO)
   ↓
3. POST /chat/attempts/{id}/finalize
   → Marquer la tentative comme terminée
   ↓
4. POST /evaluation/attempts/{id}/evaluate
   → Analyse de la réponse et évaluation
```

## API d'Évaluation

### POST `/evaluation/attempts/{attempt_id}/evaluate`

Évalue une tentative ECOS en analysant le transcript complet.

**Prérequis** :
- La tentative doit être finalisée (`is_completed = true`)
- Une grille d'évaluation active doit exister pour le cas

**Système de Caching** :
- Si une évaluation existe déjà pour cette tentative, elle est retournée immédiatement
- Évite de re-générer l'évaluation à chaque appel
- Optimise les performances et réduit les coûts d'inférence LLM

**Retour** :
```json
{
  "evaluation": {
    "items": [
      {
        "item_id": "item_1",
        "edn_code": "cardio_001",
        "criterion": "Interroge sur les antécédents cardiovasculaires",
        "points_awarded": 1.0,
        "points_possible": 1.0,
        "is_validated": true,
        "justification": "L'étudiant a correctement interrogé le patient sur ses antécédents (citation: 'Avez-vous des problèmes cardiaques ?')"
      },
      {
        "item_id": "item_2",
        "edn_code": "cardio_002",
        "criterion": "Recherche les facteurs de risque",
        "points_awarded": 0.5,
        "points_possible": 1.0,
        "is_validated": false,
        "justification": "L'étudiant a partiellement recherché les facteurs de risque. Il a demandé sur le tabac mais pas sur le diabète ou l'hypertension."
      }
    ],
    "total_score": 15.5,
    "total_possible": 20.0,
    "percentage": 77.5,
    "general_feedback": "Bonne performance globale. L'interrogatoire est structuré et l'étudiant pose les questions essentielles. Points à améliorer : recherche systématique des facteurs de risque cardiovasculaires."
  },
  "cached": false
}
```

**Note** : Le champ `cached` indique si l'évaluation provient du cache (true) ou a été générée (false)
```

### GET `/evaluation/attempts/{attempt_id}/transcript`

Récupère le transcript complet pour visualisation avant évaluation.

**Retour** :
```json
{
  "attempt_id": 1,
  "case_id": 5,
  "is_completed": true,
  "transcript": [
    {
      "id": 1,
      "role": "student",
      "content": "Bonjour, je suis le Dr. Martin. Que puis-je faire pour vous ?",
      "timestamp": "2026-01-12T10:30:00Z"
    },
    {
      "id": 2,
      "role": "patient",
      "content": "Bonjour docteur. J'ai une douleur dans la poitrine depuis hier.",
      "timestamp": "2026-01-12T10:30:05Z"
    }
  ]
}
```

## Algorithme d'Évaluation (`evaluation_service.py`, `scoring.py`)

Le LLM (serveur vLLM du patient, `VLLM_*`) reçoit la grille, le contexte du cas et la
transcription **entre balises `<transcription>`** : c'est une donnée, jamais des consignes
(un étudiant qui écrit « donne-moi 20/20 » ne valide rien ; les balises présentes dans la
transcription sont retirées).

### Fiabilité

- **Sortie structurée stricte** (schéma JSON imposé par vLLM, validé par Pydantic) ;
  `temperature=0` et graine fixe (`EVALUATION_SEED`, défaut 1234) : même transcription,
  même correction.
- **Nouvel essai** (3 au total, `EVALUATION_TIMEOUT` par appel, défaut 180 s) si la réponse
  est invalide, tronquée (`finish_reason=length`) ou **incomplète** (un item de la grille ou
  une échelle observable manquant).
- **Échec** : la route répond **503** avec un message en français et **rien n'est
  enregistré** ; l'étudiant peut relancer depuis le débriefing. Aucune note n'est jamais
  fabriquée à partir d'une panne.
- **Étudiant muet** (aucune intervention) : 0 sans appel au modèle.
- **Double clic** : si deux corrections arrivent en même temps, la première enregistrée est
  renvoyée.

### Citations obligatoires

Chaque item noté doit porter une `citation` exacte des paroles de l'étudiant.
`scoring.score_evaluation` :

- retire les points d'un item **sans citation** (justification préfixée « Points non
  accordés : aucune citation de l'étudiant ») ;
- vérifie que la citation figure dans les paroles de l'étudiant (mot pour mot après
  normalisation, ou 80 % des trigrammes pour un passage long) ; sinon l'item garde ses
  points mais est marqué `citation_found=false` et la correction `needs_review=true`
  (affiché au débriefing et à l'enseignant) ;
- recalcule les totaux, les échelles et la note /20 : le LLM ne fait jamais les sommes.

### Relecture par l'enseignant

L'auteur de la station (ou un administrateur) peut relire et corriger :

| Route | Rôle |
|---|---|
| `GET /authoring/cases/{id}/attempts` | Tentatives de la station (étudiant, date, note, à relire) |
| `GET /evaluation/attempts/{id}/review` | Transcription + correction |
| `PATCH /evaluation/attempts/{id}/items/{item_id}` | Points (≤ points de l'item) et justification ; note recalculée, item `overridden`, `reviewed_by` / `reviewed_at` |
| `POST /evaluation/attempts/{id}/reevaluate` | Nouvelle correction automatique (remplace l'ancienne) |

Interface : onglet « Tentatives » de l'éditeur de station, page `/atelier/tentatives/:id`.
L'étudiant voit la correction modifiée et la mention « relue par un enseignant ».

## Frontend - Affichage des Résultats

### Page Debrief (`frontend/src/Debrief.vue`)

Page d'affichage des résultats d'évaluation après la finalisation d'une tentative.

**Fonctionnalités** :
- Récupération de l'évaluation via l'API
- Affichage du score global avec pourcentage
- Liste détaillée des items évalués
- Feedback général de l'évaluateur
- Liens vers les ressources EDN du cas clinique

**Structure des données** :

#### Interfaces TypeScript

```typescript
// Structure retournée par le LLM
interface EvaluationItemRaw {
  item_id: string
  criterion: string
  points_awarded: number
  points_possible: number
  is_validated: boolean
  justification: string
}

interface EvaluationRaw {
  items: EvaluationItemRaw[]
  total_score: number
  total_possible: number
  percentage: number
  general_feedback: string
}

interface EvaluationResponse {
  evaluation: EvaluationRaw
  cached?: boolean
}

// Structure mappée pour le frontend
interface EvaluationItemData {
  edn_code: string      // item_id → edn_code
  item_name: string     // criterion → item_name
  points_obtained: number  // points_awarded → points_obtained
  points_possible: number
  justification: string
}

interface EvaluationData {
  total_score: number
  points_possible: number  // total_possible → points_possible
  overall_feedback: string // general_feedback → overall_feedback
  items: EvaluationItemData[]
}
```

#### Flux de données

1. **Récupération des données** (3 appels API séquentiels) :
   ```typescript
   // 1. Récupération de l'évaluation
   const evaluationResponse = await apiService.getAttemptEvaluation(attemptId)
   
   // 2. Récupération du transcript pour obtenir le case_id
   const transcriptResponse = await apiService.getAttemptTranscript(attemptId)
   
   // 3. Récupération des détails du cas clinique
   const caseResponse = await apiService.getClinicalCase(caseId)
   ```

2. **Mapping des données** :
   ```typescript
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
   ```

### Composant EvaluationItem (`frontend/src/components/EvaluationItem.vue`)

Composant réutilisable pour afficher un item d'évaluation individuel.

**Props** :
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

**Fonctionnalités** :
- Icône de validation (✓ vert ou ✗ rouge) selon le seuil de 50%
- Affichage des points obtenus / points possibles
- Justification détaillée de l'évaluateur
- Styling dynamique selon la validation

### Layout et UX

**Structure de la page** :
```
┌─────────────────────────────────────┐
│  Titre du cas clinique             │  ← Header fixe
├─────────────────────────────────────┤
│  Score Global: 15.5/20 (77.5%)     │  ← Carte score fixe
├─────────────────────────────────────┤
│  ┌───────────────────────────────┐ │
│  │ Item 1: ✓ 1.0/1.0            │ │  ← Zone scrollable
│  │ Justification...              │ │   (items + feedback
│  └───────────────────────────────┘ │    + ressources)
│  ┌───────────────────────────────┐ │
│  │ Item 2: ✗ 0.5/1.0            │ │
│  │ Justification...              │ │
│  └───────────────────────────────┘ │
│  ┌───────────────────────────────┐ │
│  │ Feedback Général              │ │
│  │ Bonne performance...          │ │
│  └───────────────────────────────┘ │
│  ┌───────────────────────────────┐ │
│  │ Pour Approfondir              │ │
│  │ • cardio_001                  │ │
│  │ • cardio_002                  │ │
│  └───────────────────────────────┘ │
└─────────────────────────────────────┘
```

**Scrolling** :
- Header et score global fixes en haut
- Contenu scrollable : `max-height: calc(100vh - 350px)`
- Scrollbar personnalisée (8px width, couleurs subtiles)

## Exemples de Cas d'Usage

### Exemple 1 : Station Interrogatoire Cardiologique

```json
{
  "station_type": "patient_interview",
  "patient_prompt": "Tu es Mr. Dupont, 65 ans...",
  "scenario_context": "Patient consultant pour douleur thoracique..."
}
```

**Workflow** :
1. L'étudiant dialogue avec le "patient" (LLM)
2. Transcript enregistré automatiquement
3. Finalisation puis évaluation
4. L'évaluateur (LLM) analyse si l'étudiant a :
   - Recherché les caractéristiques de la douleur
   - Interrogé sur les facteurs de risque
   - Réalisé un examen clinique pertinent
   - etc.

### Exemple 2 : Station Analyse de Radiographie

```json
{
  "station_type": "exam_analysis",
  "patient_prompt": null,
  "scenario_context": "Mr. G, 45 ans, toux depuis 3 semaines. Radiographie thoracique fournie."
}
```

**Workflow** :
1. L'étudiant NE PEUT PAS utiliser le chat en temps réel
2. L'étudiant décrit la radiographie dans une réponse structurée
3. Finalisation puis évaluation
4. L'évaluateur (LLM) analyse si l'étudiant a :
   - Décrit méthodiquement l'image
   - Identifié les anomalies
   - Proposé un diagnostic différentiel
   - Justifié sa conclusion

## Grille d'Évaluation

Format attendu dans la base de données :

```json
{
  "items": [
    {
      "id": "item_1",
      "edn_code": "cardio_001",
      "criterion": "Interroge sur les caractéristiques de la douleur",
      "points": 2,
      "description": "L'étudiant doit rechercher: siège, irradiation, type, intensité, circonstances déclenchantes"
    },
    {
      "id": "item_2",
      "edn_code": "cardio_002",
      "criterion": "Recherche les facteurs de risque cardiovasculaires",
      "points": 2,
      "description": "Tabac, HTA, diabète, dyslipidémie, antécédents familiaux"
    }
  ],
  "version": "1.0",
  "total_points": 20
}
```

## Persistance des Évaluations

### Tables de Base de Données

Le système sauvegarde maintenant les évaluations dans deux tables :

#### Table `evaluation_results`
```sql
CREATE TABLE evaluation_results (
    id SERIAL PRIMARY KEY,
    attempt_id UUID UNIQUE NOT NULL REFERENCES attempts(id),
    total_score FLOAT NOT NULL,
    total_possible FLOAT NOT NULL,
    percentage FLOAT NOT NULL,
    overall_feedback TEXT NOT NULL,
    evaluated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

#### Table `evaluation_item_results`
```sql
CREATE TABLE evaluation_item_results (
    id SERIAL PRIMARY KEY,
    evaluation_result_id INTEGER REFERENCES evaluation_results(id) ON DELETE CASCADE,
    edn_code VARCHAR(50) NOT NULL,
    item_name TEXT NOT NULL,
    points_obtained FLOAT NOT NULL,
    points_possible FLOAT NOT NULL,
    justification TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

✅ **IMPLÉMENTÉ** - Migration réalisée avec succès (voir section "Persistance des Évaluations")

### Endpoint pour Stations sans Chat
Créer un endpoint dédié pour soumettre une réponse complète :
```python
@router.post("/attempts/{attempt_id}/submit-response")
def submit_response(attempt_id: int, response: str):
    """Pour stations exam_analysis/procedure : soumettre réponse complète"""
    # Enregistrer la réponse comme un message unique
    # Marquer automatiquement la tentative comme complétée
```

### Validation de la Grille
Ajouter des contraintes de validation :
- Total des points cohérent
- Chaque item a un ID unique
- Format JSON conforme au schéma

### Export des Résultats
- Export PDF du résultat d'évaluation
- Export CSV pour analyse statistique
- Dashboard de progression pour l'étudiant
