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
  }
}
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

## Algorithme d'Évaluation

Le LLM reçoit :
1. **Le transcript complet** de la tentative
2. **La grille d'évaluation** avec tous les critères
3. **Le contexte du cas** (titre, consignes, scénario)

Le LLM produit :
- ✅ **Points attribués** pour chaque item de la grille
- ✅ **Justification** avec citation du transcript
- ✅ **Score total** et pourcentage
- ✅ **Feedback général** constructif et pédagogique

### Règles d'Évaluation

```python
# Configuration du LLM pour l'évaluation
temperature=0.3  # Plus bas pour cohérence et objectivité
response_mime_type="application/json"  # Force le format structuré
```

**Consignes au LLM** :
- Être objectif et se baser UNIQUEMENT sur le transcript
- Ne pas inventer d'informations absentes du transcript
- Citer des passages précis pour justifier les points
- Si un élément attendu n'apparaît pas → point non attribué
- Feedback constructif et pédagogique

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

## TODO : Améliorations Futures

### Sauvegarde des Évaluations
Créer une table `EvaluationResults` pour persister les évaluations :
```sql
CREATE TABLE evaluation_results (
    id SERIAL PRIMARY KEY,
    attempt_id INTEGER REFERENCES attempts(id),
    evaluation_data JSONB,  -- Le JSON complet retourné par le LLM
    total_score FLOAT,
    total_possible FLOAT,
    percentage FLOAT,
    evaluated_at TIMESTAMP,
    evaluated_by INTEGER REFERENCES users(id)
);
```

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

## Migration depuis l'Ancien Système

### Changements Majeurs

❌ **SUPPRIMÉ** :
- `evaluator_prompt` dans `ClinicalCase`
- `generate_evaluator_reply()` dans `ai_chat_utils.py`
- Mode "évaluateur en chat" dans `chat_routes.py`

✅ **AJOUTÉ** :
- `evaluate_attempt_with_llm()` pour évaluation post-examen
- Routes `/evaluation/attempts/{id}/evaluate` et `/transcript`
- Modèles Pydantic `EvaluationItemOut`, `EvaluationResultOut`, `EvaluationOut`
- Vérification du type de station avant autorisation du chat

### Migration de la Base de Données

```sql
-- Retirer la colonne evaluator_prompt (si migration Alembic)
ALTER TABLE clinical_cases DROP COLUMN evaluator_prompt;

-- Ajouter des commentaires sur patient_prompt
COMMENT ON COLUMN clinical_cases.patient_prompt IS 
  'Prompt pour role-play patient. Obligatoire pour patient_interview, diagnosis_announcement, mixed. NULL pour exam_analysis, procedure.';
```

### Code Existant à Mettre à Jour

Si du code appelait l'ancien système :

```python
# ❌ ANCIEN (ne fonctionne plus - supprimé)
response = generate_evaluator_reply(
    evaluator_prompt=case.evaluator_prompt,  # Ce champ n'existe plus
    scenario_context=case.scenario_context,
    history=history,
    student_message=message
)

# ✅ NOUVEAU (après finalisation de la tentative)
# L'évaluation ne se fait PLUS en temps réel pendant le chat
# Elle se fait après la fin de la station via l'API d'évaluation
evaluation = evaluate_attempt_with_llm(
    transcript=full_transcript,
    evaluation_grid=grid.items,
    case_context=case_context
)
```

**Philosophie :** L'évaluateur observe silencieusement et évalue APRÈS, pas pendant.
evaluation = evaluate_attempt_with_llm(
    transcript=full_transcript,
    evaluation_grid=grid.items,
    case_context=case_context
)
```

## Résumé

| Aspect | Ancien Système | Nouveau Système |
|--------|---------------|-----------------|
| Évaluateur en chat | ✅ Mode "correcteur" en temps réel | ❌ Supprimé (non réaliste) |
| Évaluation | ❌ Pas implémentée | ✅ Post-examen avec grille |
| Stations sans patient | ⚠️ Mode évaluateur confus | ✅ Pas de chat, réponse unique |
| Format de sortie | Texte libre | JSON structuré |
| Justifications | Non | Oui, avec citations |
| Fidélité ECOS | ⚠️ Partielle | ✅ Complète |
