# Stations d'Examen Écrit (exam_analysis, procedure)

## Vue d'ensemble

Les stations de type `exam_analysis` et `procedure` n'ont **pas de conversation en temps réel** avec un patient simulé. L'étudiant :
1. Voit l'énoncé et l'iconographie (radio, ECG, etc.)
2. Rédige une réponse libre dans un champ texte
3. Soumet sa réponse
4. Reçoit une évaluation automatique via la grille

---

## Types de stations concernés

| `station_type` | Label | Modalité |
|----------------|-------|----------|
| `exam_analysis` | Analyse d'examens (radio, ECG, labo) | Iconographie + réponse écrite |
| `procedure` | Démonstration de geste technique | Énoncé + réponse écrite |

Les types `patient_interview`, `diagnosis_announcement` et `mixed` utilisent le **chat** — voir `SSE_STREAMING.md`.

---

## Workflow complet

```
1. Dashboard → bouton "Voir plus" → popup instructions
2. Dashboard → bouton "Commencer" → POST /chat/attempts (création attempt)
3. Routing automatique → /written-exam/{attemptId}
4. WrittenExamView charge :
   - GET /chat/attempts/{id}/case-info          (titre, type, durée)
   - GET /chat/attempts/{id}/exam-attachments   (iconographie show_at_start=true)
5. Étudiant rédige sa réponse (champ textarea)
6. Étudiant soumet → POST /chat/attempts/{id}/submit-answer
7. Auto-finalisation → POST /chat/attempts/{id}/finalize
8. Redirection → /debrief/{attemptId}
9. Débrief → POST /evaluation/attempts/{id}/evaluate
```

---

## API Backend

### Créer un attempt
```http
POST /chat/attempts
Body: {"case_id": 1}

Response: {"id": "uuid", "case_id": 1, "is_completed": false, ...}
```

### Récupérer l'iconographie
```http
GET /chat/attempts/{attempt_id}/exam-attachments

Response:
[
  {
    "id": "uuid",
    "filename": "ecg.jpg",
    "display_name": "ECG 12 dérivations",
    "kind": "image",
    "mime_type": "image/jpeg",
    "file_url": "/files/images/1/...",
    "show_at_start": true
  }
]
```

Seuls les attachments avec `show_at_start = true` sont retournés.

### Soumettre la réponse
```http
POST /chat/attempts/{attempt_id}/submit-answer
Body: {"answer": "Je vois une opacité alvéolaire de la base droite..."}

Response: {"status": "ok", "message": "Réponse enregistrée avec succès."}
```

- Peut être appelé plusieurs fois (la réponse précédente est remplacée)
- Retourne 408 si le temps est écoulé
- Retourne 400 si la station est de type chat (pas écriture)

### Finaliser
```http
POST /chat/attempts/{attempt_id}/finalize

Response: {"status": "ok", "completed_at": "2026-03-25T10:30:00"}
```

### Évaluer
```http
POST /evaluation/attempts/{attempt_id}/evaluate

Response: {
  "items": [...],
  "total_score": 8,
  "total_possible": 10,
  "percentage": 80.0,
  "general_feedback": "..."
}
```

Le transcript utilisé par l'évaluateur contient la réponse soumise via `submit-answer` (stockée comme `Message(role=student)`).

---

## Gestion de l'iconographie

### Flag `show_at_start`

Le champ `show_at_start` sur le modèle `Attachment` distingue deux types de pièces jointes :

| `show_at_start` | Quand affiché | Endpoint |
|-----------------|---------------|----------|
| `true` | Dès le début de l'examen (stations écrites) | `GET /exam-attachments` |
| `false` | Déclenché par mots-clés dans le chat | `trigger_keywords` |

### Uploader une iconographie

```bash
POST /attachments/upload
Content-Type: multipart/form-data

file: ecg.jpg
case_id: 1
display_name: ECG 12 dérivations
kind: image
show_at_start: true   ← IMPORTANT pour les stations écrites
trigger_keywords:     ← laisser vide pour l'iconographie fixe
```

### Types de fichiers supportés

| Kind | Types MIME | Affichage frontend |
|------|------------|-------------------|
| `image` | image/jpeg, image/png, image/webp | `<img>` avec lightbox |
| `document` | application/pdf | `<iframe>` ou lien téléchargement |
| `video` | video/mp4 | `<video>` |

---

## Frontend (`WrittenExamView.vue`)

### Layout

```
┌──────────────────────────────────────────────────────┐
│ ExamHeader : [Titre cas] • [Type station] • [Timer]  │
├─────────────────────────┬────────────────────────────┤
│  PANNEAU GAUCHE         │  PANNEAU DROIT             │
│                         │                            │
│  📋 Énoncé              │  ✍️ Votre réponse           │
│  [student_instructions] │  [textarea]                │
│                         │                            │
│  🖼️ Iconographie        │  [Soumettre]               │
│  [images/PDF]           │                            │
└─────────────────────────┴────────────────────────────┘
```

### Comportement timer

- Le timer est géré par `ExamHeader` (sans bouton "Terminer" contrairement à `ChatHeader`)
- À expiration, `WrittenExamView` soumit automatiquement la réponse partielle
- Redirection automatique vers `/debrief/{id}` après 3 secondes

### Routage automatique

Dans `Dashboard.vue`, la constante `WRITTEN_EXAM_STATION_TYPES` détermine la vue :

```typescript
import { WRITTEN_EXAM_STATION_TYPES } from './services/api';

function getAttemptRoute(stationTypeValue: string, attemptId: string): string {
    return WRITTEN_EXAM_STATION_TYPES.includes(stationTypeValue)
        ? `/written-exam/${attemptId}`   // exam_analysis, procedure
        : `/chat/${attemptId}`;           // patient_interview, etc.
}
```

`WRITTEN_EXAM_STATION_TYPES = ['exam_analysis', 'procedure']`

---

## Créer un cas de type `exam_analysis`

### 1. Créer le cas (via admin ou API)

```json
{
  "title": "Interprétation ECG - Fibrillation Atriale",
  "station_type": "exam_analysis",
  "scenario_context": "Mme L, 68 ans, consulte pour des palpitations depuis 3 jours.",
  "student_instructions": "Analysez cet ECG et proposez une prise en charge initiale.",
  "patient_prompt": null,
  "duration_seconds": 300
}
```

### 2. Uploader l'iconographie

```bash
curl -X POST http://localhost:8000/attachments/upload \
  -F "file=@ecg_fa.jpg" \
  -F "case_id=1" \
  -F "display_name=ECG 12 dérivations" \
  -F "kind=image" \
  -F "show_at_start=true"
```

### 3. Créer la grille d'évaluation

```json
{
  "case_id": 1,
  "items": [
    {
      "id": "item_1",
      "criterion": "Identifie l'absence d'ondes P régulières",
      "points": 2,
      "description": "L'étudiant doit mentionner l'absence d'ondes P ou leur irrégularité"
    },
    {
      "id": "item_2",
      "criterion": "Nomme le rythme : fibrillation atriale (FA)",
      "points": 3
    },
    {
      "id": "item_3",
      "criterion": "Propose anticoagulation + contrôle fréquence",
      "points": 3
    }
  ]
}
```

---

## Cas `procedure`

Identique à `exam_analysis`, mais sans iconographie obligatoire. L'énoncé décrit la procédure à réaliser et la réponse de l'étudiant détaille les étapes.

```json
{
  "title": "Pose d'une voie veineuse périphérique",
  "station_type": "procedure",
  "student_instructions": "Décrivez les étapes de pose d'une VVP chez un patient conscient.",
  "duration_seconds": 240
}
```

---

## Migration des données existantes

Pour marquer des attachments existants comme iconographie :

```sql
-- Marquer un attachment comme show_at_start
UPDATE attachments SET show_at_start = true WHERE id = 'uuid-de-lattachment';

-- Voir tous les attachments d'un cas avec leur flag
SELECT id, display_name, show_at_start FROM attachments WHERE case_id = 1;
```

La migration Alembic `c7f3a9d12e84` ajoute la colonne `show_at_start` avec valeur par défaut `false` pour tous les attachments existants.
