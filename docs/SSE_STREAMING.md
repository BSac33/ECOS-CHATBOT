# SSE Streaming pour le Chat Patient

## Pourquoi le streaming ?

Sans streaming, l'étudiant attend 15-20 secondes après chaque message avant de voir la réponse du patient simulé. Avec le streaming SSE, **les premiers mots apparaissent en ~1-2 secondes**, réduisant drastiquement la latence perçue.

---

## Architecture

```
Frontend                     Backend                        vLLM
   │                             │                             │
   │──POST /chat/stream──────────►│                             │
   │                             │──classify_arbiter──────────►│
   │◄─── SSE connection open ────│      (~1-2s)                │
   │                             │◄─── arbiter result ─────────│
   │                             │──generate_patient_stream───►│
   │◄─── token "Bon" ────────────│◄── chunk "Bon" ─────────────│
   │◄─── token "jour" ───────────│◄── chunk "jour" ────────────│
   │◄─── token "," ──────────────│◄── chunk "," ───────────────│
   │         ...                 │         ...                 │
   │◄─── event: done ────────────│  (persist to DB)            │
```

**Séquence :**
1. Le frontend envoie `POST /chat/attempts/{id}/chat/stream`
2. Le backend ouvre immédiatement une connexion SSE
3. L'arbitre tourne dans un thread (≈1-2s)
4. Si le message est bloqué → event `done` immédiat avec message de refus
5. Si accepté → streaming token par token depuis vLLM via queue asyncio
6. Event `done` final avec persistance en base

---

## Format SSE

### Token partiel
```
data: {"type": "token", "content": "Bon"}

data: {"type": "token", "content": "jour"}

```

### Fin du streaming
```
data: {"type": "done", "patient_reply": "Bonjour, je ne me sens pas bien.", "attachments": null}

```

### Message bloqué (ABUSIVE ou META)
```
data: {"type": "done", "patient_reply": "Votre message a été bloqué...", "attachments": null}

```

---

## Endpoint Backend

```
POST /chat/attempts/{attempt_id}/chat/stream
Content-Type: application/json
Body: {"message": "Depuis quand avez-vous cette douleur ?"}

Response: text/event-stream
```

**Codes d'erreur HTTP** (retournés avant l'ouverture du stream) :
| Code | Cause |
|------|-------|
| 404  | Attempt introuvable ou appartient à un autre utilisateur |
| 400  | Attempt déjà complété, ou station sans chat patient |
| 408  | Temps imparti écoulé |
| 500  | Patient prompt manquant |

---

## Implémentation Backend (`chat_routes.py`)

```python
@router.post("/attempts/{attempt_id}/chat/stream")
async def chat_stream(attempt_id, payload, session, user):
    # Validation identique à /chat
    ...

    async def event_stream():
        # 1. Arbitre en thread séparé
        arbiter = await asyncio.to_thread(classify_student_message_vllm_arbiter, ...)

        # 2. Si bloqué → event done immédiat
        if arbiter_blocks:
            yield f"data: {json.dumps({'type': 'done', ...})}\n\n"
            return

        # 3. Streaming via asyncio.Queue + thread executor
        loop = asyncio.get_running_loop()
        q: asyncio.Queue = asyncio.Queue()

        def run_stream():
            for chunk in generate_patient_reply_vllm_stream(...):
                loop.call_soon_threadsafe(q.put_nowait, chunk)
            loop.call_soon_threadsafe(q.put_nowait, None)  # sentinel

        stream_future = loop.run_in_executor(None, run_stream)

        full_reply = ""
        while True:
            item = await q.get()
            if item is None:
                break
            full_reply += item
            yield f"data: {json.dumps({'type': 'token', 'content': item})}\n\n"

        await stream_future

        # 4. Persist messages to DB
        session.add(student_msg)
        session.add(reply_msg)
        session.commit()

        yield f"data: {json.dumps({'type': 'done', ...})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
```

**Note sur `asyncio.Queue` :** Les générateurs Python synchrones ne peuvent pas être utilisés directement dans un contexte async. La queue agit comme pont entre le thread vLLM et l'event loop FastAPI.

---

## Implémentation Frontend (`ChatView.vue`)

Le frontend utilise `fetch` avec `ReadableStream` (pas `EventSource` qui ne supporte que GET).

```typescript
async function handleSendMessage(messageContent: string) {
    // 1. Ajout optimiste du message étudiant
    messages.value.push(studentMessage);

    // 2. Placeholder patient (rempli progressivement)
    const patientMessage = { role: 'patient', content: '' };
    messages.value.push(patientMessage);

    // 3. Fetch SSE
    const response = await fetch(`/chat/attempts/${attemptId}/chat/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ message: messageContent })
    });

    // 4. Lire le stream ligne par ligne
    const reader = response.body!.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() ?? '';

        for (const line of lines) {
            if (!line.startsWith('data: ')) continue;
            const event = JSON.parse(line.slice(6).trim());

            if (event.type === 'token') {
                patientMessage.content += event.content;
                // Vue réactif : la modification de patientMessage.content
                // met à jour l'UI automatiquement
            }
        }
    }
}
```

---

## Paramètres de génération

| Paramètre | Valeur | Rôle |
|-----------|--------|------|
| `temperature` | 0.4 | Légère variabilité naturelle |
| `max_tokens` | 100 | Cap à ~80 mots → réponses concises |
| `top_p` | 0.9 | Nucleus sampling |

Le cap à **100 tokens** est intentionnel : le patient simulé doit répondre en 1-3 phrases courtes. Des réponses plus longues allongent inutilement le délai.

---

## Comparaison des endpoints

| | `/chat` | `/chat/stream` |
|-|---------|----------------|
| Méthode | POST | POST |
| Réponse | JSON complet | SSE tokens |
| Latence perçue | 15-20s | ~1-2s (1er token) |
| Arbiter | Parallèle avec génération | Séquentiel (puis stream) |
| Persistance DB | À la fin | À la fin du stream |
| Compatible Gemini | Oui | Non (vLLM uniquement) |

---

## Débogage

```bash
# Tester le stream en CLI
curl -X POST http://localhost:8000/chat/attempts/{id}/chat/stream \
  -H "Content-Type: application/json" \
  -b cookies.txt \
  -d '{"message": "Depuis quand avez-vous mal ?"}' \
  --no-buffer

# Sortie attendue :
# data: {"type": "token", "content": "Depuis"}
# data: {"type": "token", "content": " hier"}
# data: {"type": "token", "content": " soir"}
# ...
# data: {"type": "done", "patient_reply": "Depuis hier soir, docteur.", "attachments": null}
```
