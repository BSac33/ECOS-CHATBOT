# 🎙️ Mode vocal

Deux façons de parler au patient :

- **Consultation orale (mains libres)** — bouton casque 🎧. Le micro reste ouvert, l'étudiant
  parle naturellement, le patient répond quand il a fini sa phrase, et l'étudiant peut lui
  couper la parole en parlant. **Pas de texte à l'écran par défaut** : avatar du patient,
  statut, niveau du micro et informations de l'examinateur (constantes, ECG…). La
  transcription reste générée et enregistrée pour la correction, et peut être affichée.
- **Appuyer pour parler** — bouton micro 🎤 dans la zone de saisie, avec le texte affiché :
  utile dans un environnement bruyant.

Un tour vocal
suit **exactement le même chemin qu'un tour écrit** : arbitre en parallèle, agent patient
avec outils, notes de l'examinateur, persistance (voir `docs/PATIENT_AGENT.md`). Seules
l'entrée (reconnaissance vocale) et la sortie (synthèse vocale) changent.

## Architecture

```
Navigateur                          Backend FastAPI                        GPU
──────────                          ───────────────                        ───
micro ─ AudioWorklet 24 kHz ─┐
                             │ WebSocket /chat/attempts/{id}/voice
                             ├──────► VoiceConversation ──► STT Kyutai (stt-1b-en_fr)
                             │            │  transcription      mots en direct
                             │            ▼
                             │        _run_turn (arbitre ∥ patient, outils, base)
                             │            │  texte du patient
                             │            ▼
haut-parleur ◄─ trames ──────┘        WordChunker ──mot à mot──► TTS Kyutai (tts-1.6b-en_fr)
 (lecture planifiée)                      ◄──────── audio en flux ─────────┘
```

| Fichier | Rôle |
|---|---|
| `backend_ecos_chatbot/app/kyutai_voice.py` | Clients STT/TTS (protocole WebSocket + msgpack de moshi-server), découpage du texte en mots |
| `backend_ecos_chatbot/app/voice_routes.py` | WebSocket `/chat/attempts/{id}/voice`, orchestration d'une conversation |
| `frontend/src/services/voice.ts` | Micro (AudioWorklet), lecture de la voix, coupure de parole |
| `frontend/src/ChatView.vue` | Bouton micro, sous-titres, affichage commun écrit/vocal |
| `voice/docker-compose.yml` | Serveurs Kyutai (moshi-server) |

## Consultation orale (mains libres)

```
micro ouvert ──► STT en continu (une connexion pour toute la consultation)
                    │ mots            │ probabilité de pause (Step.prs[2])
                    ▼                 ▼
             phrase en cours ──► pause > 0,6 (ou 2 s sans mot) ──► marqueur + silence
                                                                    │ derniers mots
                                                                    ▼
                                                       transcription ──► tour (comme l'écrit)
```

| Situation | Comportement |
|---|---|
| L'étudiant finit sa phrase | Fin détectée par le modèle (probabilité de pause > **0,6**, seuil d'Unmute), ou au bout de 2 s sans nouveau mot ; marqueur + ~0,6 s de silence injecté pour récupérer les derniers mots sans attendre le délai du modèle en temps réel |
| L'étudiant parle pendant que le patient parle | **2 mots** (hors écho) suffisent à couper la voix du patient ; ces mots commencent la nouvelle phrase. La réplique coupée reste enregistrée |
| L'étudiant reprend avant que le patient ait parlé (faux départ) | La réponse en préparation est annulée (rien n'était enregistré) et la phrase continue : une seule question complète est enregistrée (`turn_cancelled`) |
| Le micro entend la voix du patient (pas de casque) | **Filtre d'écho** : pendant la voix du patient et 1,5 s après, les mots reconnus qui figurent dans sa réplique sont ignorés |

## Couper la parole au patient : comptabilisé

En ECOS, **on ne coupe pas la parole au patient**. Chaque coupure est enregistrée et compte
dans la correction.

| Ce qui compte | Ce qui ne compte pas |
|---|---|
| Parler par-dessus le patient (mains libres) : `voice` | Un chevauchement sur son **dernier mot** (il avait fini) |
| Reprendre le micro pendant qu'il parle (appuyer pour parler) : `push_to_talk` | Un **faux départ** (le patient n'avait pas encore parlé) |
| Cliquer « Interrompre le patient » : `button` | |

**Ce qui a réellement été dit.** La synthèse Kyutai horodate chaque mot (messages `Text`
avec `start_s`). Au moment de la coupure, le serveur connaît la durée de voix jouée par le
navigateur (signal `playback started`, à défaut l'envoi de la première trame), donc les mots
prononcés. Sur le message du patient :
- `content` garde la réplique complète générée ;
- `spoken_content` contient ce qui a été prononcé (« Oui, dans le bras gauche et … ») ;
- `interrupted_by` donne la façon dont il a été coupé.

**Conséquences :**
- **Correction** : la réplique apparaît comme `PATIENT (coupé par l'étudiant): …` avec la
  seule partie prononcée, et l'en-tête `[COMMUNICATION ORALE]` donne le nombre de coupures.
  Consigne de l'évaluateur : un item d'écoute ou de compétences relationnelles n'est pas
  validé à partir de **2 coupures** (seuil réglable dans le prompt de `vllm_chat_utils.py`),
  et toute coupure est mentionnée dans le retour.
- **Debrief** : section « Écoute du patient » avec le nombre de coupures et, pour chacune,
  ce que le patient disait et **ce que l'étudiant n'a pas entendu** (souvent une information
  clinique : un item de la grille).
- **Réalisme** : le patient ne « se souvient » que de ce qu'il a dit, et sait qu'on l'a
  coupé ; il peut le faire remarquer (« Je n'avais pas fini… »), surtout si ça se répète.
- La coupure est signalée au navigateur (`patient_interrupted`) après le `done` de la
  réplique, même si elle a eu lieu avant son enregistrement.

Le serveur ne sait pas quand le navigateur a fini de jouer l'audio reçu (la synthèse va plus
vite que le temps réel) : le navigateur le lui signale (`playback started/ended`).

**Casque recommandé.** La voix du patient est jouée par Web Audio, que l'annulation d'écho
du navigateur ne couvre pas toujours ; le filtre d'écho compense, mais un casque reste le
plus fiable.

En mode vocal, le patient reçoit des consignes de **style oral** (phrases courtes,
hésitations naturelles, nombres en toutes lettres, aucun symbole).

## Déroulé d'une prise de parole (appuyer pour parler)

1. **Clic sur le micro** → `{"type": "start"}`. Le serveur ouvre une connexion de
   reconnaissance vocale ; l'audio envoyé avant qu'elle soit prête est mis en file d'attente.
2. **L'étudiant parle** → trames binaires float32 24 kHz (80 ms). Les mots reconnus
   reviennent en direct (`transcript_partial`) : sous-titres dans la bulle de l'étudiant.
3. **Second clic** → `{"type": "stop"}`. Le serveur envoie un **marqueur** suivi de silence
   (plus vite que le temps réel) : le marqueur revient une fois tout l'audio transcrit,
   délai du modèle (~0,5 s) compris → `transcript_final`.
4. **Tour** : même orchestration que l'écrit. La synthèse vocale est ouverte **pendant**
   que l'arbitre et le patient réfléchissent, pour masquer le temps de connexion.
5. **Voix** : chaque mot complet du patient est envoyé à la synthèse dès qu'il est prêt ;
   l'audio est relayé au navigateur qui le planifie bout à bout.

Le texte du patient n'est envoyé à la synthèse **qu'après validation par l'arbitre** :
un message bloqué ne produit jamais de voix.

### Découpage en mots (`WordChunker`)

La synthèse Kyutai attend des mots entiers, alors que le LLM produit des morceaux.
- Un mot n'est envoyé que lorsque le suivant a commencé (il peut être incomplet :
  « commen » + « cé »).
- La ponctuation isolée de la typographie française est rattachée au mot précédent :
  « ça ? » → « ça? ».
- « 8/10 » est lu « 8 sur 10 ».

### Couper la parole au patient

Appuyer sur le micro pendant que le patient parle (ou cliquer « Couper ») coupe **sa voix
immédiatement**, côté navigateur puis côté serveur. **Le texte de sa réplique continue
d'arriver et est enregistré** : couper la parole ne fait jamais perdre un échange. Le tour
suivant attend que le précédent soit enregistré, pour que l'historique du patient soit complet.

## Protocole WebSocket

| Sens | Message | Rôle |
|---|---|---|
| → | `{"type": "conversation_start"}` / `{"type": "conversation_stop"}` | consultation mains libres : micro ouvert en continu |
| → | `{"type": "playback", "state": "started"\|"ended"}` | la voix du patient joue / s'est tue (navigateur) |
| → | `{"type": "start"}` | début de prise de parole (coupe la voix du patient) |
| → | binaire | audio du micro, PCM float32 little-endian, mono, 24 kHz |
| → | `{"type": "stop"}` | fin de prise de parole |
| → | `{"type": "interrupt"}` | couper la voix du patient |
| ← | `ready {voice}` | connexion prête, voix du patient |
| ← | `listening` | la reconnaissance vocale écoute |
| ← | `transcript_partial {text}` / `transcript_final {text}` | sous-titres / transcription (vide = rien entendu) |
| ← | `delta`, `examiner_note`, `done`, `error` | comme le flux SSE de l'écrit |
| ← | binaire | voix du patient, PCM float32 little-endian, mono, 24 kHz |
| ← | `audio_end` / `interrupted` | fin de la voix / voix coupée |
| ← | `turn_cancelled` | faux départ : la phrase de l'étudiant continue |
| ← | `patient_interrupted {message_id, reason, spoken_content}` | coupure de parole enregistrée (comptée dans la correction) |
| ← | `conversation_stopped` | micro fermé |
| ← | `voice_unavailable {message}` | synthèse indisponible : la réplique reste écrite |

Sécurité : authentification par le cookie `access_token` (comme le reste de l'API) et
contrôle de l'en-tête `Origin` (même origine ou `CORS_ORIGINS`), pour empêcher un autre
site d'ouvrir la connexion avec le cookie de l'étudiant.

## Lancer les serveurs Kyutai

```bash
cd voice
HUGGING_FACE_HUB_TOKEN=hf_... docker compose up -d   # 1er démarrage : compilation + téléchargement (~10 min)
```

Puis dans `backend_ecos_chatbot/fastapi.env` :

```bash
KYUTAI_STT_URL=ws://<serveur-gpu>:8090
KYUTAI_TTS_URL=ws://<serveur-gpu>:8089
KYUTAI_API_KEY=public_token          # = authorized_ids des configs voice/moshi-server/configs/*.toml
KYUTAI_TTS_DEFAULT_VOICE=unmute-prod-website/developpeuse-3.wav
```

Mémoire GPU indicative (chiffres d'Unmute) : STT ~2,5 Go, TTS ~5,3 Go. Le budget vLLM
(0,55 + 0,25 de la L40S) laisse ~9 Go. `batch_size` dans les configs = nombre de connexions
simultanées : en reconnaissance, une **consultation orale** occupe une place pendant toute
sa durée (une prise de parole « appuyer pour parler » seulement le temps de parler) ; en
synthèse, une place par réplique en cours.

En développement, le proxy Vite transmet le WebSocket (`ws: true` sur `/chat/attempts`).

## Choisir la voix d'un patient

Champ `voice_id` du cas clinique (API admin) : chemin relatif dans le dépôt Hugging Face
[`kyutai/tts-voices`](https://huggingface.co/kyutai/tts-voices). Voix françaises :
- `cml-tts/fr/*.wav` : 35 locuteurs du corpus CML-TTS (CC-BY 4.0), à écouter sur
  Hugging Face pour choisir selon l'âge et le sexe du patient ;
- `unmute-prod-website/developpeuse-3.wav` (femme), `unmute-prod-website/fabieng-enhanced-v2.wav` (homme).

Sans `voice_id`, la voix `KYUTAI_TTS_DEFAULT_VOICE` est utilisée.

## Données

- **Aucun enregistrement audio n'est conservé** : seule la transcription est enregistrée
  (`chat_messages.modality = "voice"`), comme un message écrit.
- Reconnaissance et synthèse tournent sur vos serveurs : la voix des étudiants ne quitte
  pas l'infrastructure.
- L'évaluation porte sur la transcription : une erreur de reconnaissance peut coûter un
  item. Les sous-titres en direct permettent à l'étudiant de s'en apercevoir.

## Tests

```bash
cd backend_ecos_chatbot/app
pytest tests/test_kyutai_voice.py tests/test_voice_route.py
```

Les tests utilisent de **faux serveurs Kyutai** (`tests/fake_kyutai.py`) qui parlent le vrai
protocole (WebSocket, msgpack, clé d'API, marqueurs) et simulent les pauses (probabilité de
pause qui monte dans le silence, segments de parole successifs) : clients, découpage en
mots, tour vocal complet, coupure de parole (bouton et voix), filtre d'écho, faux départ
fusionné, fin de phrase de repli, message bloqué sans voix, services indisponibles,
silence, tentative expirée, authentification et contrôle d'origine.

## Suite prévue

- Voix de l'examinateur pour les résultats d'examen.
- Long silence de l'étudiant : le patient pourrait relancer (« Docteur… ? »), comme Unmute
  le fait après 7 s.
- Régler les seuils (pause 0,6, 2 mots pour couper la parole) sur de vraies consultations.
