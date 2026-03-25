# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**ECOS Chatbot** is a web-based clinical examination simulation platform for medical students. It simulates ECOS (Examen Clinique Objectif Structuré / Objective Structured Clinical Examination) stations where students interact with AI-powered patient simulations and receive automated evaluations based on structured grids.

### Tech Stack
- **Backend**: FastAPI + SQLAlchemy/SQLModel + PostgreSQL
- **Frontend**: Vue 3 + TypeScript + Vite + PrimeVue
- **AI**: Google Gemini API (default) + vLLM (optional) with structured output
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

**AI Utilities:**
- `ai_chat_utils.py` - Gemini API integration for patient simulation
- `vllm_chat_utils.py` - vLLM integration with structured output (Pydantic schemas)
- Uses **structured output** with Pydantic models to enforce JSON schema compliance

**Storage:**
- `storage.py` - Local file storage for attachments
- `storage/` directory - Uploaded files (PDFs, images, etc.)

### Frontend Structure (`frontend/src/`)

**Main Views:**
- `App.vue` - Root component with router-view
- `Dashboard.vue` - Case selection dashboard for students
- `ChatView.vue` - Interactive patient interview interface
- `Debrief.vue` - Post-evaluation results display

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
→ Creates Attempts record with UUID
→ Sets expires_at based on case.duration_seconds
```

**2. Chat (for patient_interview stations only)**
```
POST /chat/attempts/{id}/chat
Body: {"message": "Bonjour, que puis-je faire pour vous?"}
→ Saves student message in chat_messages table
→ Calls AI (Gemini/vLLM) with patient_prompt + history
→ Returns patient reply + optional attachments
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
→ Calls LLM with structured output (Pydantic)
→ Returns EvaluationResultOut with items + scores + feedback
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

# LLM Provider: "gemini" or "vllm"
LLM_PROVIDER=gemini

# Gemini Configuration
GEMINI_API_KEY=your-api-key
GEMINI_MODEL=gemini-1.5-flash

# vLLM Configuration (if using vLLM)
VLLM_BASE_URL=http://localhost:8001/v1
VLLM_MODEL=meta-llama/Llama-3.1-8B-Instruct
VLLM_API_KEY=token-abc123
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
The arbiter LLM evaluates whether students attempt to extract scenario details, grading rubrics, or manipulate the simulation. See evaluation logic in `chat_routes.py` and evaluation prompts.

### Error Handling
- vLLM calls use exponential backoff retry (3 attempts)
- Fallback to empty evaluation result on complete failure
- Pydantic validation with graceful degradation to raw JSON if schema fails

## Testing

```bash
# Backend unit tests (if implemented)
cd backend_ecos_chatbot/app
pytest

# Frontend type checking
cd frontend
npm run build  # Runs vue-tsc -b

# Full workflow test via CLI
make test
```

## Common Tasks

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
- `docs/ATTACHMENTS.md` - File attachment system (includes `show_at_start` for iconography)
- `docs/WRITTEN_EXAM.md` - Written exam stations (exam_analysis, procedure) — frontend/API workflow
- `docs/SSE_STREAMING.md` - SSE streaming endpoint for patient chat (latency optimization)
- `docs/USER_ROUTES.md` - User API documentation
- `docs/POSTGRESQL_SETUP.md` - Database setup guide
- `docs/FRONTEND_DEBRIEF.md` - Debrief page implementation
- `CLI_GUIDE.md` - Comprehensive CLI usage guide

## Database Schema Overview

**Core Tables:**
- `users` - Student/teacher/admin accounts
- `clinical_cases` - ECOS station definitions
- `attempts` - Student attempt sessions
- `chat_messages` - Conversation transcripts
- `evaluation_grids` - Assessment criteria (JSON column)
- `evaluation_results` - Cached evaluation summaries
- `evaluation_item_results` - Individual item scores for analytics
- `attachments` - Case resources (images, PDFs, etc.)

**Link Tables** (Many-to-Many):
- `case_edn_link` - Cases ↔ EDN items
- `case_discipline_link` - Cases ↔ Medical disciplines
- `edn_discipline_link` - EDN items ↔ Disciplines
