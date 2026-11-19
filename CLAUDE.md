# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**ECOS Chatbot** is a web-based clinical examination simulation platform for medical students. It simulates ECOS (Examen Clinique Objectif Structuré / Objective Structured Clinical Examination) stations where students interact with AI-powered patient simulations and receive automated evaluations based on structured grids.

### Tech Stack
- **Backend**: FastAPI + SQLAlchemy/SQLModel + PostgreSQL
- **Frontend**: Vue 3 + TypeScript + Vite + PrimeVue
- **AI**: vLLM (Qwen) with structured output; the Google Gemini path (`ai_chat_utils.py`) is legacy, do not use it for new features
- **Deployment**: Docker Compose
- **CLI**: Typer-based Python CLI for testing

## Development Commands

### Quick Start
```bash
# Full setup: start services, migrate DB, seed data
make setup
make seed

# Or reset everything from scratch
make reset

# Import the official cardiology reference (CNEC/SFC) used by the case authoring assistant
make corpus

# Import private station packs (book content, never in git) from backend_ecos_chatbot/app/private/stations/
make stations
```

### Production / deployment (see `docs/DEPLOYMENT.md`)
```bash
# Application (PostgreSQL + API + nginx serving the built frontend), no GPU
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml exec api python scripts/create_user.py admin --role admin

# Models on the GPU machine (DMZ): vLLM patient + arbiter, Kyutai STT/TTS (profile "voix").
# Access mode set in deploy/dmz/.env: direct (default, docker-compose.direct.yml: ports bound to
# MODELS_BIND only, vLLM key, no TLS; tests over VPN or behind an existing nginx) or the nginx
# gateway (profile "passerelle": TLS, single API key, IP allowlist). Profiles: llm (vLLM, default),
# voix, passerelle. No room on Docker's partition / no admin: LLMs outside Docker with
# deploy/dmz/vllm-local.sh (same .env; vLLM version picked from the NVIDIA driver's CUDA version),
# voice image built for the driver's CUDA (KYUTAI_CUDA_VERSION)
cd deploy/dmz && cp .env.example .env && docker compose up -d --build
```

### Backend
```bash
# Start backend services (PostgreSQL + FastAPI)
cd backend_ecos_chatbot && docker-compose up -d

# View logs
make logs

# Access PostgreSQL shell
make db-shell

# Stop services
make stop

# Clean everything (including volumes)
make clean
```

### Frontend
```bash
cd frontend
npm install
npm run dev      # Development server on port 5173
npm run build    # Production build
npm run preview  # Preview production build
```

### CLI Testing
```bash
# Activate Python virtual environment
source .venv/bin/activate

# Quick workflow
python ecos_cli.py start             # Interactive: login + select case + chat

# Individual commands
python ecos_cli.py login             # Login and save session
python ecos_cli.py list-cases        # List available clinical cases
python ecos_cli.py chat-loop 1       # Start interactive chat for case ID 1
python ecos_cli.py attempt-evaluate <attempt-id>  # Evaluate completed attempt
python ecos_cli.py user-stats        # View user statistics
```

### Database Migrations
```bash
cd backend_ecos_chatbot/app

# Create new migration
alembic revision --autogenerate -m "description"

# Apply migrations
alembic upgrade head

# Rollback migration
alembic downgrade -1
```

## Architecture

### Backend Structure (`backend_ecos_chatbot/app/`)

**Core Files:**
- `main.py` - FastAPI application entry point with CORS and router registration
- `models.py` - SQLModel database models (users, cases, attempts, messages, evaluations)
- `db.py` - Database session management

**Route Modules:**
- `auth.py` - JWT authentication with HttpOnly cookies
- `chat_routes.py` - Chat sessions and attempt management (create, chat, finalize)
- `case_routes.py` - Clinical case listing and details (public access)
- `user_routes.py` - User statistics and attempt history
- `admin_routes.py` - Case and evaluation grid management (admin only)
- `attachment_routes.py` - File upload/download for case resources
- `evaluation_routes.py` - Post-exam evaluation with LLM
- `authoring_routes.py` - Case authoring workshop for teachers (`/authoring`): drafts, compiled preview, checks, versioned publish, teacher test attempts, assistant, reference search, optional peer review (`review_status` a_relire/relue, never blocks publication; reviewers get read-only access and can test). See `docs/CASE_AUTHORING.md`

**Case Authoring:**
- `case_sheet.py` - Structured case sheet (facts, not prompts: patient words, spontaneous vs on-question disclosure, pertinent negatives, never-says terms, grid linked to facts) compiled into patient prompt / evaluator context / grid / exam findings; `check_sheet` role-maintenance checks (erreur blocks publication)
- `case_publishing.py` - `publish()` freezes a `CaseVersion` and updates the case runtime fields, grid and EDN links; `snapshot(..., "test")` for teacher test attempts
- `authoring_assistant.py` - "Générer" actions (interview, negatives, lay wording, persona, grid, exam) grounded on the official corpus, structured output, deterministic filtering; proposals marked `generated=True` until the teacher validates them. vLLM server (`AUTHORING_*`, defaults to `VLLM_*`)
- `corpus.py` - Official 2nd-cycle reference: SFC/CNEC chapter parser (R2C item, starting situations, ranked objectives, ranked excerpts), idempotent `store_chapter`, BM25 `search_corpus`. Import: `scripts/ingest_corpus.py`. Texts live in the DB only, never in the repo (agreement of the cardiology college and UNESS; tests use a fictitious chapter)
- `case_examples.py` - Dupont case as a structured sheet (used by the seed and tests)
- Station formats: `station.domain` (11 ECOS-N domains), `station.interlocutor` (`patient` | `professionnel`: simulated health professional (PSS) with its own role rules in `patient_agent.PROFESSIONAL_RULES`, never does the student's work | `aucun`: no PS/PSS, the student talks alone, nothing replies), `station.documents` (vignette documents shown at start), attitude scales (0-4) + global rating, teaching content shown at debrief
- `scoring.py` - Recomputes item totals, attitude scales and the /20 score (`20 × ((1−p)·items + p·scales/4)`, p = `attitude_weight`, default 0.25); never trusts LLM sums
- `station_packs.py` - Private station packs (JSON sheets + images, dir or .zip) imported idempotently by `clinical_cases.source_key`; `scripts/import_stations.py`; the seed imports `private/stations/` (git-ignored) and `STATION_PACKS`. Protected content (e.g. the author's ECOS book) must never be committed: the repository is public

**AI Utilities:**
- `ai_chat_utils.py` - Gemini API integration for patient simulation
- `vllm_chat_utils.py` - vLLM integration with structured output (Pydantic schemas)
- `arbiter.py` - Fast student-message arbiter: lexical prefilter (instant block), LRU verdict cache, minimal LLM call (`{"category","tone"}` JSON, fixed system prompt for vLLM prefix caching, reused client, `ARBITER_TIMEOUT` then fail-open). Benchmark: `scripts/arbiter_bench.py`
- `kyutai_voice.py` - Kyutai STT/TTS clients (moshi-server WebSocket + msgpack protocol, 24 kHz float32 PCM), `WordChunker` (LLM text deltas -> whole words for TTS)
- `voice_routes.py` - Voice mode WebSocket `/chat/attempts/{id}/voice`: push-to-talk (`start`/`stop`) or hands-free consultation (`conversation_start`: continuous STT, end of turn when pause probability > 0.6, barge-in by voice with echo filter, false-start merge). STT -> shared `_run_turn` -> TTS word by word; barge-in cuts the voice only, the reply text is still persisted. Interrupting the patient is an ECOS fault: recorded on the patient message (`interrupted_by` voice|push_to_talk|button, `spoken_content` = words actually spoken, from TTS word timestamps), used in patient history, evaluation transcript and debrief. See `docs/VOICE.md`
- `patient_agent.py` - Patient agent with tool calling (examiner tools: `afficher_document`, `resultat_examen_clinique`, `signaler_hors_cadre`). Tool execution is pure; the route applies events only after the arbiter allows the message. See `docs/PATIENT_AGENT.md`
- Uses **structured output** with Pydantic models to enforce JSON schema compliance

**Storage:**
- `storage.py` - Local file storage for attachments
- `storage/` directory - Uploaded files (PDFs, images, etc.)

### Frontend Structure (`frontend/src/`)

**Main Views:**
- `App.vue` - Root component with router-view
- `Dashboard.vue` - Case selection dashboard for students
- `ChatView.vue` - Interactive patient interview interface (text via SSE, push-to-talk, hands-free oral consultation)
- `components/VoiceConsultation.vue` - Oral consultation screen: no text by default (transcript still persisted), patient status, mic level, examiner notes
- `Debrief.vue` - Post-evaluation results display
- `authoring/` - Case authoring workshop (`/atelier`, teachers/admins): `AuthoringCases.vue`, `CaseEditor.vue` (tabs, autosave, checks, test, publish), `FactsEditor.vue`, `GridEditor.vue`, `AssistantPanel.vue`, `CorpusSearch.vue`, `api.ts`

**Components:**
- `ChatHeader.vue` - Case info + countdown timer
- `Message.vue` - Chat message bubble
- `Textbox.vue` - Student message input
- `EvaluationItem.vue` - Individual evaluation criterion display
- `CasesList.vue` - Clinical case cards with filters
- `LoginForm.vue` - Authentication form

**Services:**
- `services/api.ts` - HTTP client wrapper for backend API calls
- `stores/` - Pinia state management (auth, user)
- `router/` - Vue Router configuration

### Key Concepts

#### Station Types
Defined in `models.py` as `StationType` enum:
- `patient_interview` - Requires real-time chat (patient role-play)
- `diagnosis_announcement` - Announcement simulation with chat
- `exam_analysis` - No chat, single written response (ECG, X-ray analysis)
- `procedure` - No chat, procedure demonstration
- `mixed` - Combination of above

#### Workflow

**1. Case Attempt Creation**
```
POST /chat/attempts
Body: {"case_id": 1}
→ Creates Attempts record with UUID, bound to the latest published CaseVersion
  (attempts.case_version_id): chat, voice and evaluation use that frozen version
→ Sets expires_at based on the version duration
→ Students cannot start a draft; teachers test drafts via POST /authoring/cases/{id}/test
  (attempts.is_test, excluded from user stats)
→ Start messages: instructions + vignette documents (examiner messages with attachment)
```

**2. Chat (for patient_interview stations only)**
```
POST /chat/attempts/{id}/chat/stream   (SSE: delta / examiner_note / done / error — used by the frontend)
POST /chat/attempts/{id}/chat          (same orchestration, full JSON response — used by the CLI)
WS   /chat/attempts/{id}/voice         (voice mode: mic audio in, patient voice out, same orchestration)
Body: {"message": "Bonjour, que puis-je faire pour vous?"}
→ Arbiter (vLLM 3B) and patient agent run IN PARALLEL; patient text is buffered
  until the arbiter verdict, then streamed (shared `_run_turn` in chat_routes.py)
→ If arbiter blocks: patient generation cancelled, nothing stored in transcript,
  moderation_events row (action="blocked"), ChatOut.blocked=true
→ Else saves student + patient messages, plus "examiner" messages for tool results
  (exam findings, documents shown) and moderation_events for flags
→ Returns patient reply + attachments + examiner_notes
→ Station without interlocutor (version sheet interlocutor="aucun"): only the student message is
  stored, ChatOut.silent=true, no patient/arbiter/TTS
```

**3. Finalization**
```
POST /chat/attempts/{id}/finalize
→ Sets is_completed=true and completed_at timestamp
→ Required before evaluation
```

**4. Evaluation**
```
POST /evaluation/attempts/{id}/evaluate
→ Retrieves full transcript from chat_messages
→ Loads evaluation_grids for the case
→ Calls LLM with structured output (Pydantic): items + attitude scales + global rating
→ scoring.score_evaluation recomputes totals and score_20
→ Returns EvaluationResultOut with items + scales + global_performance + score_20 + feedback
→ Saves to evaluation_results + evaluation_item_results tables (cached)
```

#### Authentication System
- Uses **JWT tokens stored in HttpOnly cookies** (not localStorage)
- `auth.py` provides `check_authorization` dependency
- Cookie saved in `~/.ecos_cookies.json` for CLI
- CORS configured with `allow_credentials=True` for cookie support

#### Evaluation System

**Philosophy**: The evaluator observes silently and evaluates AFTER, never during the exam (like real ECOS).

**Structured Output**: Uses Pydantic models (`EvaluationOutput`, `EvaluationResult`, `EvaluationItem`) to enforce JSON schema. See `vllm_chat_utils.py` and `docs/STRUCTURED_OUTPUT.md`.

**Caching**: Evaluations are persisted in database and returned from cache on subsequent calls to avoid redundant LLM inference.

**Evaluation Grid Format** (`evaluation_grids.items` JSON column):
```json
{
  "items": [
    {
      "id": "item_1",
      "edn_code": "cardio_001",
      "criterion": "Interroge sur les antécédents cardiovasculaires",
      "points": 2,
      "description": "L'étudiant doit rechercher..."
    }
  ]
}
```

## Environment Configuration

### Backend (`backend_ecos_chatbot/fastapi.env`)
```bash
DATABASE_URL=postgresql://user:pass@database:5432/dbname
SECRET_KEY=your-secret-key
CORS_ORIGINS=http://localhost:5173,http://localhost:3000

# LLM provider: vllm (gemini is legacy, never required)
LLM_PROVIDER=vllm

# Models (DMZ gateway in production, see deploy/dmz/README.md)
VLLM_BASE_URL=https://modeles.ihu.local/patient/v1
VLLM_MODEL=Qwen/Qwen3-8B
VLLM_API_KEY=<MODELS_API_KEY>
VLLM_ARBITER_BASE_URL=https://modeles.ihu.local/arbitre/v1
VLLM_ARBITER_MODEL=Qwen/Qwen2.5-3B-Instruct
VLLM_ARBITER_API_KEY=<MODELS_API_KEY>
KYUTAI_STT_URL=wss://modeles.ihu.local/stt
KYUTAI_TTS_URL=wss://modeles.ihu.local/tts
KYUTAI_API_KEY=<MODELS_API_KEY>
# SSL_CERT_FILE=/etc/ssl/ecos/ca-bundle.pem   # gateway certificate signed by an internal CA

# Case authoring assistant (empty = VLLM_* above)
AUTHORING_BASE_URL=
AUTHORING_MODEL=
AUTHORING_API_KEY=
```

### Frontend (`frontend/.env.local`)
```bash
VITE_API_URL=http://localhost:8000
```

### CLI
```bash
export ECOS_BASE_URL=http://localhost:8000
export ECOS_TOKEN=optional-jwt-token  # If not using cookies
```

## Important Design Patterns

### Patient Simulation Prompts
Located in `ai_chat_utils.py::build_patient_system_instruction()`. Key rules:
- Patient responds naturally in 1-3 sentences
- Only reveals information when asked explicitly
- Never uses medical jargon or acts as evaluator
- If no explicit question, only expresses emotion + short non-medical question

### Anti-Cheat Measures
The arbiter (`arbiter.py`) blocks `ABUSIVE` and `META_EXFILTRATION` messages (attempts to extract the grid, scenario, prompt, or to break the patient's role) and flags `OFF_TOPIC` / aggressive tone in `moderation_events`. Blocked messages never reach the transcript and the patient generation is cancelled.

### Error Handling
- vLLM calls use exponential backoff retry (3 attempts)
- Fallback to empty evaluation result on complete failure
- Pydantic validation with graceful degradation to raw JSON if schema fails

## Testing

```bash
# Backend unit tests (SQLite in memory + simulated LLM, no GPU/Postgres needed)
cd backend_ecos_chatbot/app
pip install -r requirements-dev.txt
pytest
# Against a migrated PostgreSQL: TEST_DATABASE_URL=postgresql://... pytest tests/test_chat_route.py

# Frontend type checking
cd frontend
npm run build  # Runs vue-tsc -b

# Full workflow test via CLI
make test
```

## Common Tasks

### Create a Clinical Case
Use the workshop (`/atelier`, teacher role): fill the structured sheet, follow the checks, use
"Générer", test the patient, publish. Do not hand-write patient prompts: they are compiled from
the sheet (`case_sheet.compile_case`). In code/seed: build a `CaseSheet` and call
`case_publishing.publish()` (see `seed_database.py`).

### Add a New Station Type
1. Add enum value to `StationType` in `models.py`
2. Update station type validation in `chat_routes.py`
3. Create appropriate patient_prompt template in case creation
4. Update frontend case selection UI

### Add a New Route
1. Create route file in `backend_ecos_chatbot/app/`
2. Define Pydantic models for request/response
3. Register router in `main.py` with `app.include_router()`
4. Update frontend `services/api.ts` with new API call

### Create a New Migration
```bash
# After modifying models.py
cd backend_ecos_chatbot/app
alembic revision --autogenerate -m "Add new_field to table_name"
alembic upgrade head
```

### Switch LLM Provider
Set `LLM_PROVIDER=vllm` in `fastapi.env` and configure vLLM endpoint. The code automatically routes to `vllm_chat_utils.py` instead of `ai_chat_utils.py`.

## Documentation References

- `docs/EVALUATION.md` - Comprehensive evaluation system documentation
- `docs/STRUCTURED_OUTPUT.md` - Pydantic structured output implementation
- `docs/STATION_TYPES.md` - Station type definitions
- `docs/PATIENT_AGENT.md` - Patient agent tool calling, guardrails, moderation events
- `docs/CASE_AUTHORING.md` - Case authoring workshop: structured sheet, compilation, checks, versions, assistant, official corpus (sources and rights), API
- `docs/DEPLOYMENT.md` - Production deployment: app compose (`docker-compose.prod.yml`, nginx SSE/WebSocket proxying, accounts, seed, packs, corpus), models on the DMZ (`deploy/dmz/`), internal CA, network flows
- `docs/VOICE.md` - Voice mode: architecture, WebSocket protocol, Kyutai servers (`voice/docker-compose.yml`), voices
- `docs/ATTACHMENTS.md` - File attachment system
- `docs/USER_ROUTES.md` - User API documentation
- `docs/POSTGRESQL_SETUP.md` - Database setup guide
- `docs/FRONTEND_DEBRIEF.md` - Debrief page implementation
- `CLI_GUIDE.md` - Comprehensive CLI usage guide

## Database Schema Overview

**Core Tables:**
- `users` - Student/teacher/admin accounts
- `clinical_cases` - ECOS station definitions (`sheet`: structured case sheet being edited; runtime fields = latest published version; `review_status` + `reviewed_*`: optional peer review; `source_key`: private pack import key)
- `case_versions` - Frozen compiled versions (`published` | `test`); `attempts.case_version_id` = version played
- `attempts` - Student attempt sessions (`case_version_id`: version played; `is_test`: teacher test, excluded from stats)
- `chat_messages` - Conversation transcripts (roles: system, student, patient, examiner; `modality` text|voice; `interrupted_by` + `spoken_content` when the student cut the patient off)
- `moderation_events` - Student misconduct (blocked by arbiter or flagged by patient agent)
- `evaluation_grids` - Assessment criteria (JSON column)
- `evaluation_results` - Cached evaluation summaries
- `evaluation_item_results` - Individual item scores for analytics
- `attachments` - Case resources (images, PDFs, etc.)
- `corpus_sources` / `corpus_chunks` - Official reference (source + rights note; ranked excerpts per R2C item and section)
- `starting_situations` / `item_situation_links` - ECOS starting situations and their R2C items (from the corpus)

**Link Tables** (Many-to-Many):
- `case_edn_link` - Cases ↔ EDN items
- `case_discipline_link` - Cases ↔ Medical disciplines
- `edn_discipline_link` - EDN items ↔ Disciplines
