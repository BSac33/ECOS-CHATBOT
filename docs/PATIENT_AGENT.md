# 🩺 Agent patient avec outils (tool calling)

## Vue d'ensemble

Le patient simulé n'est plus un simple générateur de texte : c'est un **agent** qui
peut appeler des outils. Les outils jouent le rôle de l'**examinateur** (jamais celui
du patient). Le patient reste dans son personnage, et l'examinateur transmet les
informations objectives à l'étudiant.

Module : `backend_ecos_chatbot/app/patient_agent.py`
Routes (`chat_routes.py`), qui partagent la même orchestration :
- `POST /chat/attempts/{id}/chat/stream` : réponse en flux **SSE**, utilisée par le frontend
- `POST /chat/attempts/{id}/chat` : réponse JSON complète, utilisée par la CLI et les anciens clients

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
   └──► agent patient (Qwen3-8B + outils) ──┤   le texte du patient est mis en TAMPON
                                            ▼   tant que l'arbitre n'a pas tranché
                    verdict de l'arbitre
          ┌─────────────────┴─────────────────┐
     bloqué                                  accepté
     - génération patient annulée            - tampon vidé, puis texte relayé en direct
     - aucun texte du patient envoyé         - à la fin : messages étudiant + patient,
     - rien dans le transcript                 messages "examiner", moderation_events
     - moderation_event "blocked"              "flagged" (outil patient, ton agressif
     - ChatOut.blocked = true                  ou hors sujet selon l'arbitre)
```

Le temps avant le premier mot est donc max(arbitre, premier token du patient). Il n'y a
**aucun** risque qu'un morceau de réponse parte avant la validation du message.

## Arbitre (`arbiter.py`)

Comme le texte du patient attend le verdict, l'arbitre fixe le délai avant le premier mot.
Il prend donc toujours le chemin le plus rapide :

| Étape | Coût | Rôle |
|---|---|---|
| 1. Préfiltre lexical | ≈ 0 ms | Insultes explicites et demandes flagrantes (grille, corrigé, prompt, « ignore tes instructions »). Message bloqué **sans appel LLM et sans lancer le patient**. Motifs à haute précision : « grille costale », « clinique », « dispute », « n'oubliez pas les consignes » passent. |
| 2. Cache des verdicts | ≈ 0 ms | « Bonjour », « D'accord », « Merci »… reviennent d'un étudiant à l'autre (LRU, messages ≤ 200 caractères). |
| 3. Appel LLM minimal | ~16 tokens générés | Sortie `{"category", "tone"}` uniquement, prompt système **fixe** (gardé par le cache de préfixe vLLM), `temperature=0`, client HTTP réutilisé. |
| 4. Repli | ≤ `ARBITER_TIMEOUT` | Délai dépassé ou serveur indisponible : message **accepté** (le préfiltre a déjà écarté les cas flagrants), incident journalisé. |

Catégories : `CLINICAL_QUESTION`, `EXAM_REQUEST`, `EMPATHY`, `CLOSING`, `META_BENIGN`,
`META_EXFILTRATION`, `OFF_TOPIC`, `ABUSIVE`, `OTHER`.
- **Bloquées** : `ABUSIVE`, `META_EXFILTRATION`.
- **Signalées** (conservées dans le transcript) : `OFF_TOPIC`, ton `AGGRESSIVE` ou `INSULTING`.

Gains mesurés avec le tokenizer de Qwen2.5, par rapport à l'ancien arbitre :

| | Ancien | Nouveau |
|---|---|---|
| Tokens générés (JSON avec espaces) | 61 | 18 |
| Tokens générés (JSON indenté) | 79 | 22 |
| Prompt total | 998 | 613 |
| Partie variable du prompt (hors cache de préfixe) | 38 | 9 |
| Création d'un client HTTP par message | ~43 ms | 0 (réutilisé) |
| Délai maximal en cas de panne | aucun (+ pauses de 1 s et 2 s) | `ARBITER_TIMEOUT` (2 s) |

Pour mesurer la latence réelle et la justesse sur votre GPU, avec 34 messages annotés
(questions intimes, dépistage suicidaire, insultes, tentatives de triche…) :

```bash
cd backend_ecos_chatbot/app
python scripts/arbiter_bench.py --legacy                          # nouveau vs ancien
python scripts/arbiter_bench.py --model Qwen/Qwen3-1.7B          # essayer un modèle plus petit
```

## Flux SSE (`/chat/stream`)

Réponse `text/event-stream`, un JSON par événement :

| Événement | Données | Quand |
|---|---|---|
| `delta` | `{"text": "Ça a commencé "}` | morceau de la réplique du patient |
| `examiner_note` | `ExaminerNoteOut` | résultat d'outil visible (examen clinique, document) |
| `done` | `ChatOut` complet | toujours en dernier, **après** l'enregistrement en base (`blocked: true` si refusé) |
| `error` | `{"status": 502, "message": "..."}` | échec : rien n'est enregistré |

```
event: delta
data: {"text": "D'accord, "}

event: examiner_note
data: {"kind": "exam_findings", "title": "Constantes vitales", "content": "PA 158/94 mmHg ..."}

event: done
data: {"patient_reply": "D'accord, allez-y.", "blocked": false, "attachments": null, "examiner_notes": [...]}
```

- Les erreurs de validation (tentative inconnue 404, terminée 400, temps écoulé 408)
  restent des **réponses HTTP classiques**, renvoyées avant l'ouverture du flux.
- Si le client se déconnecte avant `done`, la génération vLLM est annulée et **rien n'est
  enregistré** (comme une erreur). C'est la base de la future interruption du patient en mode vocal.
- Le texte de `done.patient_reply` est la référence (ce qui est en base) ; le frontend
  remplace la bulle par ce texte à la fin.
- Si le modèle parle avant d'appeler un outil puis reprend après, les deux morceaux forment
  une seule réplique.
- Les blocs `<think>` et les balises `<tool_call>` sont filtrés **au fil du flux**, même
  quand une balise est coupée entre deux morceaux.
- Depuis FastAPI 0.106, la session injectée par `Depends(get_session)` est fermée avant
  l'envoi d'une `StreamingResponse` : le flux ouvre sa propre session pour écrire en fin de tour.
- Derrière nginx : la réponse porte `X-Accel-Buffering: no` (pas de mise en tampon par le proxy).

Côté frontend : `frontend/src/services/sse.ts` lit le flux via `fetch`, car `EventSource`
ne gère pas le POST. `ChatView.vue` crée la bulle du patient au premier `delta`.

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
VLLM_ARBITER_BASE_URL=http://localhost:8002/v1
VLLM_ARBITER_MODEL=Qwen/Qwen2.5-3B-Instruct
ARBITER_TIMEOUT=2.0             # au-delà, le message est accepté par défaut
```

vLLM doit être lancé avec `--enable-auto-tool-choice --tool-call-parser hermes`
(voir `deploy/dmz/docker-compose.yml`). Le parser `hermes` fonctionne aussi avec Qwen2.5 si
vous voulez revenir à `Qwen/Qwen2.5-7B-Instruct`.

## Tests

```bash
cd backend_ecos_chatbot/app
pip install -r requirements-dev.txt
pytest                                                   # SQLite en mémoire, LLM simulé
TEST_DATABASE_URL=postgresql://... pytest tests/test_chat_route.py   # sur une base PostgreSQL migrée
```

## Suite prévue

- Découpage du flux en phrases pour la synthèse vocale (le SSE est en place)
- Gradation des sanctions à partir de `moderation_events` (3 incidents → fin de station)
- Contrôle des phrases du patient avant envoi (termes interdits propres au cas)
- Mode vocal : reconnaissance et synthèse vocales Kyutai (« appuyer pour parler », puis conversation continue)
