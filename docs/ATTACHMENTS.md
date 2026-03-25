# 📎 Gestion des Fichiers et Attachments

## 🎯 Vue d'ensemble

Le système permet d'uploader et de gérer des fichiers multimédia associés aux cas cliniques. Les fichiers peuvent être automatiquement attachés aux réponses du LLM lorsque l'étudiant déclenche certains mots-clés.

## 📁 Structure de stockage

```
storage/
├── images/
│   └── {case_id}/
│       └── {uuid}.jpg
├── videos/
│   └── {case_id}/
│       └── {uuid}.mp4
├── documents/
│   └── {case_id}/
│       └── {uuid}.pdf
├── audio/
│   └── {case_id}/
│       └── {uuid}.mp3
└── transcripts/
    └── {case_id}/
        └── {uuid}.json
```

## 🔌 Routes API

### 1. Upload un fichier

```http
POST /attachments/upload
Content-Type: multipart/form-data

{
  "file": <fichier>,
  "case_id": 1,
  "display_name": "Électrocardiogramme",
  "description": "ECG 12 dérivations, rythme sinusal",
  "trigger_keywords": "ecg,électrocardiogramme,électro,cardiogramme",
  "show_at_start": false
}
```

**Champ `show_at_start` :**
- `false` (défaut) : attachment déclenché par `trigger_keywords` dans le chat
- `true` : attachment affiché dès le début, utilisé pour l'iconographie des stations écrites (`exam_analysis`, `procedure`)

Pour l'iconographie des stations d'examen écrit :
```http
POST /attachments/upload
{
  "file": ecg.jpg,
  "case_id": 1,
  "display_name": "ECG 12 dérivations",
  "show_at_start": true,
  "trigger_keywords": ""   ← laisser vide
}
```

**Réponse :**
```json
{
  "id": 42,
  "filename": "ecg_patient.jpg",
  "file_url": "/files/images/1/a1b2c3d4-e5f6-7890-abcd-ef1234567890.jpg",
  "kind": "image",
  "size_bytes": 524288
}
```

### 2. Récupérer les infos d'un fichier

```http
GET /attachments/{attachment_id}
```

**Réponse :**
```json
{
  "id": 42,
  "filename": "ecg_patient.jpg",
  "display_name": "Électrocardiogramme",
  "kind": "image",
  "mime_type": "image/jpeg",
  "size_bytes": 524288,
  "file_url": "/files/images/1/a1b2c3d4-e5f6-7890-abcd-ef1234567890.jpg",
  "uploaded_at": "2026-01-12T14:30:00"
}
```

### 3. Lister les fichiers d'un cas

```http
GET /attachments/case/{case_id}?available_only=true
```

**Réponse :**
```json
[
  {
    "id": 42,
    "filename": "ecg_patient.jpg",
    "display_name": "Électrocardiogramme",
    "kind": "image",
    "mime_type": "image/jpeg",
    "size_bytes": 524288,
    "file_url": "/files/images/1/...",
    "uploaded_at": "2026-01-12T14:30:00"
  },
  {
    "id": 43,
    "filename": "radio_thorax.jpg",
    "display_name": "Radiographie thorax",
    "kind": "image",
    "mime_type": "image/jpeg",
    "size_bytes": 1048576,
    "file_url": "/files/images/1/...",
    "uploaded_at": "2026-01-12T14:35:00"
  }
]
```

### 4. Télécharger un fichier

```http
GET /attachments/download/{attachment_id}
```

Retourne le fichier brut avec le bon Content-Type.

### 5. Supprimer un fichier

```http
DELETE /attachments/{attachment_id}
```

## 🤖 Détection automatique dans les conversations

Lorsqu'un étudiant envoie un message, le système détecte automatiquement si des mots-clés correspondent à des fichiers disponibles.

**Exemple :**

1. **Upload initial** (par l'enseignant) :
```python
# Upload ECG avec mots-clés
POST /attachments/upload
{
  "file": ecg.jpg,
  "case_id": 1,
  "display_name": "Électrocardiogramme",
  "trigger_keywords": "ecg,électrocardiogramme,électro"
}
```

2. **Pendant la conversation** :
```
Étudiant : "Je souhaite réaliser un électrocardiogramme"
```

3. **Réponse du système** :
```json
{
  "patient_reply": "D'accord docteur, je vais me préparer pour l'électrocardiogramme.",
  "attachments": [42]  // ← IDs des fichiers attachés
}
```

4. **Le frontend peut alors** :
```javascript
// Récupérer les infos et afficher les fichiers
const attachmentIds = response.attachments;
for (const id of attachmentIds) {
  const info = await fetch(`/attachments/${id}`);
  const attachmentData = await info.json();
  
  // Afficher l'image/vidéo/document
  displayAttachment(attachmentData);
}
```

## 🎨 Côté Frontend

```javascript
// Afficher un attachment dans le chat
function displayAttachment(attachment) {
  if (attachment.kind === 'image') {
    return `<img src="${attachment.file_url}" alt="${attachment.display_name}" />`;
  } else if (attachment.kind === 'video') {
    return `<video src="${attachment.file_url}" controls></video>`;
  } else if (attachment.kind === 'document') {
    return `<a href="/attachments/download/${attachment.id}" download>
              📄 ${attachment.display_name}
            </a>`;
  }
}
```

## 📊 Cas d'usage

### Exemple 1 : ECG
```python
# Upload
display_name: "Électrocardiogramme"
trigger_keywords: "ecg,électrocardiogramme,électro"

# Message étudiant déclencheur :
- "Je réalise un ECG"
- "Pouvez-vous faire un électrocardiogramme ?"
- "Je voudrais voir l'électro"
```

### Exemple 2 : Radio thorax
```python
display_name: "Radiographie thorax"
trigger_keywords: "radio,radiographie,thorax,poumons,rx"

# Messages déclencheurs :
- "Je demande une radio du thorax"
- "Faisons une radiographie des poumons"
```

### Exemple 3 : Résultats labo
```python
display_name: "Résultats de laboratoire"
trigger_keywords: "prise de sang,laboratoire,labo,bilan sanguin,nfs"

# Messages déclencheurs :
- "Je prescris une prise de sang"
- "Quels sont les résultats du labo ?"
```

## ⚙️ Configuration

Fichier `.env` :
```env
# Stockage local (développement)
STORAGE_TYPE=local
STORAGE_PATH=storage

# OU S3/MinIO (production)
STORAGE_TYPE=s3
S3_BUCKET=ecos-chatbot-prod
S3_ENDPOINT=https://minio.example.com  # Pour MinIO
AWS_ACCESS_KEY_ID=xxx
AWS_SECRET_ACCESS_KEY=yyy
```

## 🔒 Limites de fichiers

| Type | Extension | Taille max |
|------|-----------|------------|
| Image | .jpg, .png, .gif, .webp | 10 MB |
| Video | .mp4, .webm, .mov | 200 MB |
| Document | .pdf, .txt, .docx | 20 MB |
| Audio | .mp3, .wav, .ogg | 50 MB |
| Transcript | .json, .txt | 10 MB |

## 🚀 Migration vers le cloud

Pour passer du stockage local à S3/MinIO :

1. Changer `STORAGE_TYPE=s3` dans `.env`
2. Uploader les fichiers existants : `aws s3 sync storage/ s3://bucket/`
3. Redémarrer l'application

Aucun changement de code nécessaire ! ✨
