# 🎭 Types de Stations ECOS

Le système supporte maintenant **deux modes de fonctionnement** selon le type de station ECOS.

## 📋 Types de stations disponibles

### 1. **`patient_interview`** - Interrogatoire patient
**LLM en mode :** Impersonation patient  
**Nécessite :** `patient_prompt`  
**Exemple :**
```json
{
  "title": "Douleur thoracique",
  "station_type": "patient_interview",
  "scenario_context": "Mr. D, 55 ans, consulte pour une douleur thoracique.",
  "patient_prompt": "Tu es Mr. D. Tu as 55 ans, fumeur...",
  "student_instructions": "Interrogez le patient sur sa douleur thoracique..."
}
```

### 2. **`exam_analysis`** - Analyse d'examens
**LLM en mode :** Pas de chat en temps réel (l'étudiant soumet sa réponse complète)  
**Nécessite :** `scenario_context` uniquement  
**Évaluation :** Après finalisation via `/evaluation/attempts/{id}/evaluate`  
**Exemple :**
```json
{
  "title": "Analyse de radiographie pulmonaire",
  "station_type": "exam_analysis",
  "scenario_context": "Mr. G vient pour une toux depuis 3 semaines. Fébrile à 39°, crépitants base droite.",
  "patient_prompt": null,
  "student_instructions": "Prescrivez un examen complémentaire et décrivez ce que vous voyez."
}
```

**Note importante :** Dans un ECOS réel, l'évaluateur n'interagit PAS avec l'étudiant. L'évaluation se fait silencieusement après la fin de la station.

### 3. **`procedure`** - Procédure technique
**LLM en mode :** Pas de chat en temps réel  
**Évaluation :** Après finalisation via grille d'évaluation  
**Exemple :** Pose de voie veineuse, suture, examen clinique

### 4. **`diagnosis_announcement`** - Annonce de diagnostic
**LLM en mode :** Impersonation patient  
**Exemple :** Annoncer un cancer, une maladie chronique

### 5. **`mixed`** - Station mixte
**LLM en mode :** Adaptatif  
**Exemple :** Interrogatoire puis prescription d'examens

---

## 🔄 Logique de sélection automatique

```python
# Dans chat_routes.py
requires_patient_impersonation = case.station_type in [
    StationType.patient_interview,
    StationType.diagnosis_announcement,
    StationType.mixed
]

if not requires_patient_impersonation:
    # Stations exam_analysis et procedure n'ont PAS de chat en temps réel
    raise HTTPException(
        400, 
        "Cette station ne supporte pas le chat en temps réel. "
        "L'étudiant doit soumettre sa réponse complète puis demander l'évaluation."
    )

if not case.patient_prompt:
    raise HTTPException(500, "Station configurée sans patient_prompt")

# Mode role-play patient uniquement
reply = generate_patient_reply(
    patient_prompt=case.patient_prompt,
    history=history,
    student_message=payload.message
)
```

**Important :** L'évaluation se fait séparément via `/evaluation/attempts/{id}/evaluate`

---

## 📝 Exemples concrets

### Exemple 1 : Interrogatoire patient (avec impersonation)

```json
{
  "title": "Douleur abdominale aiguë",
  "station_type": "patient_interview",
  "scenario_context": "Hugo, 24 ans, consulte aux urgences pour douleur abdominale",
  "student_instructions": "Réalisez un interrogatoire complet. Durée : 6 minutes",
  "patient_prompt": "Tu es Hugo, 24 ans. Tu as mal au ventre depuis ce matin...",
  "duration_seconds": 360
}
```

**Conversation :**
```
Étudiant : Bonjour, où avez-vous mal ?
Patient (LLM) : Bonjour docteur, j'ai mal au ventre, ça a commencé ce matin...
```

### Exemple 2 : Analyse d'examen (sans conversation)

```json
{
  "title": "Interprétation ECG - FA",
  "station_type": "exam_analysis",
  "scenario_context": "Mme L, 68 ans, palpitations. Voici son ECG.",
  "student_instructions": "Analysez cet électrocardiogramme et proposez une prise en charge.",
  "patient_prompt": null,
  "duration_seconds": 300
}
```

**Workflow :**
```
1. L'étudiant voit le cas et l'ECG (attachment)
2. L'étudiant rédige son analyse complète
3. L'étudiant finalise sa tentative
4. Le système évalue via /evaluation/attempts/{id}/evaluate
5. Le LLM analyse : "L'étudiant a correctement identifié la fibrillation atriale..."
```

**Note :** Dans un ECOS réel, l'évaluateur observe silencieusement, il n'y a PAS de dialogue.

### Exemple 3 : Analyse radio pulmonaire

```json
{
  "title": "Pneumopathie - Radio thorax",
  "station_type": "exam_analysis",
  "scenario_context": "Mr. G vient à votre consultation pour une toux depuis 3 semaines. Les symptômes s'étaient améliorés dans un premier temps, puis la toux s'est de nouveau accentuée. Il est fébrile à 39° et l'auscultation trouve un foyer de crépitants de la base droite.",
  "student_instructions": "Prescrivez-vous un examen complémentaire? Si oui, lequel? Décrivez ce que vous voyez.",
  "patient_prompt": null,
  "duration_seconds": 420
}
```

**Attachments à créer :**
```bash
POST /attachments/upload
{
  "file": radio_thorax_base_droite.jpg,
  "case_id": 1,
  "display_name": "Radiographie thorax",
  "description": "Radio thorax face : opacité alvéolaire base droite",
  "trigger_keywords": "radio,radiographie,thorax,poumons,rx,imagerie"
}
```

**Conversation :**
```
Étudiant : Je prescris une radiographie du thorax
Examinateur (LLM) : Excellente décision. Voici la radio [image attachée]. Que voyez-vous ?
Étudiant : Je constate une opacité alvéolaire de la base droite
Examinateur (LLM) : Parfait ! Cette opacité est effectivement compatible avec une pneumopathie...
```

---

## 🔧 Migration des cas existants

Pour les cas déjà créés (avec uniquement `patient_prompt`) :

```sql
-- Par défaut, tous deviennent des interrogatoires patients
UPDATE clinical_cases 
SET 
  station_type = 'patient_interview',
  scenario_context = student_instructions
WHERE station_type IS NULL;
```

Ou manuellement selon le type réel :

```python
# Cas d'analyse à mettre à jour
case = session.get(ClinicalCase, 1)
case.station_type = StationType.exam_analysis
case.scenario_context = "Mr. G vient pour une toux..."
case.patient_prompt = None  # Pas de conversation en temps réel
session.commit()
```

**Note :** Le champ `evaluator_prompt` a été supprimé. L'évaluation se fait maintenant via `/evaluation/attempts/{id}/evaluate` qui analyse le transcript complet avec la grille d'évaluation.

---

## ✅ Avantages

1. **Flexibilité** : Un seul système pour tous types de stations
2. **Clarté** : Le type de station définit explicitement le mode
3. **Fidélité ECOS** : L'évaluateur n'interagit JAMAIS pendant l'examen
4. **Évolutivité** : Facile d'ajouter de nouveaux types
5. **Compatibilité** : Les anciens cas restent fonctionnels (mode patient par défaut)

---

## 🎯 Recommandations

- **Interrogatoire patient** → `station_type: patient_interview` + `patient_prompt`
- **Analyse d'examen** → `station_type: exam_analysis` + `scenario_context` + attachments
- **Procédure technique** → `station_type: procedure` + `scenario_context`
- **Annonce diagnostic** → `station_type: diagnosis_announcement` + `patient_prompt`

**Évaluation pour tous les types :** Utiliser `/evaluation/attempts/{id}/evaluate` après finalisation
