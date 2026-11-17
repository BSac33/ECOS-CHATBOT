# 🩺 Agent patient avec outils (tool calling)

## Vue d'ensemble

Le patient simulé n'est plus un simple générateur de texte : c'est un **agent** qui
peut appeler des outils. Les outils jouent le rôle de l'**examinateur** (jamais celui
du patient). Le patient reste dans son personnage, et l'examinateur transmet les
informations objectives à l'étudiant.

Module : `backend_ecos_chatbot/app/patient_agent.py`
Route : `POST /chat/attempts/{id}/chat` (`chat_routes.py`)

## Outils disponibles

Les outils sont construits **pour chaque cas** : un outil sans données (pas de documents,
pas d'examen clinique renseigné) n'est pas proposé au modèle.

| Outil | Quand le modèle l'appelle | Effet |
|---|---|---|
| `afficher_document` | L'étudiant demande ou prescrit explicitement un examen (« je vous fais un ECG ») | Le document (pièce jointe du cas) est montré à l'étudiant |
| `resultat_examen_clinique` | L'étudiant annonce un examen physique **précis** (« je prends votre tension ») | Les résultats sont communiqués par l'examinateur |
| `signaler_hors_cadre` | Grossièreté, propos déplacés, hors sujet, tentative de triche | Incident tracé dans `moderation_events` ; le patient répond en personnage |

### Garde-fous dans la conception

- **Pas de fuite par l'outil** : le modèle patient ne voit jamais les UUID ni la `description`
  des pièces jointes (elle peut contenir l'interprétation de l'examen), seulement le nom
  affiché et les mots-clés. Les résultats d'examen clinique ne lui sont **pas** renvoyés :
  il ne peut pas les réciter.
- **Exécution pure** : un outil n'écrit rien en base. Il produit un événement, appliqué
  par la route **seulement si l'arbitre a validé le message**.
- **Boucle bornée** : 2 tours d'outils maximum, puis réponse texte forcée (`tool_choice="none"`).
- **Nettoyage** : les blocs `<think>` et les balises `<tool_call>` mal parsées sont retirés.

## Déroulé d'un tour de chat

```
message étudiant
   ├──► arbitre (Qwen 3B, JSON contraint)  ─┐   en PARALLÈLE :
   └──► agent patient (Qwen3-8B + outils) ──┤   latence = max(arbitre, patient)
                                            ▼
                    verdict de l'arbitre
          ┌─────────────────┴─────────────────┐
     bloqué                                  accepté
     - génération patient annulée            - messages étudiant + patient
     - rien dans le transcript               - messages "examiner" (résultats, documents)
     - moderation_event "blocked"            - moderation_events "flagged" (outil patient,
     - ChatOut.blocked = true                  ton agressif ou hors sujet selon l'arbitre)
```

## Format de réponse (`ChatOut`)

```json
{
  "patient_reply": "D'accord, allez-y.",
  "attachments": ["<uuid>"],
  "blocked": false,
  "examiner_notes": [
    {"kind": "exam_findings", "title": "Constantes vitales", "content": "PA 158/94 mmHg, ..."},
    {"kind": "document", "title": "ECG 18 dérivations", "content": "L'examinateur vous montre : ECG 18 dérivations",
     "attachment_id": "<uuid>", "file_url": "/attachments/download/<uuid>", "mime_type": "image/png"}
  ]
}
```

Les champs `patient_reply` et `attachments` sont inchangés : la CLI et les anciens clients continuent de fonctionner.

## Données du cas

### Résultats d'examen clinique (`clinical_cases.exam_findings`)

```json
[
  {"id": "constantes", "label": "Constantes vitales", "findings": "PA 158/94 mmHg aux deux bras, FC 102/min..."},
  {"id": "auscultation_cardiaque", "label": "Auscultation cardiaque", "findings": "Bruits du cœur réguliers..."}
]
```

`id` : minuscules, chiffres et `_` uniquement. Il sert d'identifiant pour l'outil.
Le cas de démonstration (`seed_database.py`) en contient un exemple complet.

### Documents

Ce sont les pièces jointes du cas avec `is_available_during_case = true`. Il faut donner un
`display_name` explicite (« Bilan biologique : NFS, ionogramme, troponine ») et des
`trigger_keywords` (synonymes). Le modèle s'en sert pour choisir le bon document.

## Base de données

Migration `c4f1a9e2b7d3` :
- valeur `examiner` ajoutée à l'enum `chatrole` (messages de l'examinateur, inclus dans le
  transcript d'évaluation sous la forme `EXAMINATEUR: ...`). L'évaluateur a pour consigne
  de ne jamais valider un item sur ces seules lignes.
- colonne `clinical_cases.exam_findings` (JSON)
- table `moderation_events` (`source`, `category`, `severity`, `action`, `detail`, `student_message`)

## Configuration

`fastapi.env` :

```bash
LLM_PROVIDER=vllm               # l'agent n'est utilisé qu'avec vLLM
VLLM_MODEL=Qwen/Qwen3-8B        # mode "thinking" désactivé automatiquement pour Qwen3
PATIENT_AGENT_ENABLED=true      # false = ancien comportement (pas d'outils, documents par mots-clés)
PATIENT_AGENT_TIMEOUT=30        # secondes par appel LLM
```

vLLM doit être lancé avec `--enable-auto-tool-choice --tool-call-parser hermes`
(voir `vllm/vllm-docker-compose.yml`). Le parser `hermes` fonctionne aussi avec Qwen2.5 si
vous voulez revenir à `Qwen/Qwen2.5-7B-Instruct`.

## Tests

```bash
cd backend_ecos_chatbot/app
pip install -r requirements-dev.txt
pytest                                                   # SQLite en mémoire, LLM simulé
TEST_DATABASE_URL=postgresql://... pytest tests/test_chat_route.py   # sur une base PostgreSQL migrée
```

## Suite prévue

- Réponse en streaming (SSE), indispensable pour la synthèse vocale phrase par phrase
- Gradation des sanctions à partir de `moderation_events` (3 incidents → fin de station)
- Contrôle des phrases du patient avant envoi (termes interdits propres au cas)
- Mode vocal : reconnaissance et synthèse vocales Kyutai (« appuyer pour parler », puis conversation continue)
