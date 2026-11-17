# 🎙️ Mode vocal (« appuyer pour parler »)

L'étudiant parle au patient au micro, le patient lui répond à voix haute. Un tour vocal
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

## Déroulé d'une prise de parole

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
(0,55 + 0,25 de la L40S) laisse ~9 Go. `batch_size` dans les configs = nombre d'étudiants
pouvant parler, ou de patients pouvant répondre, **en même temps**.

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
protocole (WebSocket, msgpack, clé d'API, marqueurs) : clients, découpage en mots, tour
vocal complet, coupure de parole, message bloqué sans voix, synthèse ou reconnaissance
indisponible, silence, tentative expirée, authentification et contrôle d'origine.

## Suite prévue

- **Conversation continue** : fin de prise de parole détectée automatiquement grâce à la
  détection sémantique du modèle (`Step.prs[2]`, probabilité de pause, déjà lue par
  `STTSession.pause_probability`), sans bouton.
- **Ce qui a vraiment été dit** : en cas de coupure, n'enregistrer que la partie
  prononcée (les messages `Text` de la synthèse donnent l'horodatage de chaque mot).
- Option « masquer le texte du patient » pour entraîner l'écoute.
- Voix de l'examinateur pour les résultats d'examen.
