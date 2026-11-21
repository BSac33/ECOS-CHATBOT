"""
Point d'entrée FastAPI d'ECOS Chatbot.
"""
from __future__ import annotations

import logging
import os
from urllib.parse import urlsplit

import dotenv

# Variables d'environnement (fastapi.env en développement ; env_file de Docker en production)
dotenv.load_dotenv("fastapi.env")

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO").upper(),
                    format="%(asctime)s %(levelname)s %(name)s : %(message)s")
logger = logging.getLogger("ecos")

from fastapi import FastAPI, Request  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402
from sqlalchemy import text  # noqa: E402

from admin_routes import router as admin_router  # noqa: E402
from attachment_routes import router as attachment_router  # noqa: E402
from auth import router as auth_router  # noqa: E402
from authoring_routes import router as authoring_router  # noqa: E402
from case_routes import router as case_router  # noqa: E402
from chat_routes import router as chat_router  # noqa: E402
from db import engine  # noqa: E402
from evaluation_routes import router as evaluation_router  # noqa: E402
from user_routes import router as user_router  # noqa: E402
from voice_routes import router as voice_router  # noqa: E402

# ==================== CONFIGURATION ====================

PLACEHOLDERS = ("changez_moi", "changeme", "your-secret-key", "your_production_api_key")


def check_configuration() -> None:
    """Refuse de démarrer avec une valeur d'exemple non remplacée (fichiers *.example)."""
    for name in ("SECRET_KEY", "DATABASE_URL"):
        value = (os.getenv(name) or "").lower()
        if any(p in value for p in PLACEHOLDERS):
            raise RuntimeError(f"{name} contient encore une valeur d'exemple : remplacez-la dans fastapi.env")
    if len(os.getenv("SECRET_KEY") or "") < 32:
        logger.warning("SECRET_KEY courte : utilisez au moins 32 caractères aléatoires (openssl rand -hex 32)")
    if os.getenv("LLM_PROVIDER", "vllm").lower() != "vllm":
        logger.warning("LLM_PROVIDER=%s ignoré : seul vLLM est pris en charge", os.getenv("LLM_PROVIDER"))


check_configuration()

docs_enabled = os.getenv("DOCS_ENABLED", "false").lower() in ("1", "true", "yes")
app = FastAPI(title="ECOS Chatbot API",
              docs_url="/docs" if docs_enabled else None,
              redoc_url="/redoc" if docs_enabled else None,
              openapi_url="/openapi.json" if docs_enabled else None)

# CORS : origines exactes (cookies HttpOnly : pas de joker avec allow_credentials)
allowed_origins = [o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:3000,http://localhost:5173").split(",")
                   if o.strip()]
app.add_middleware(CORSMiddleware, allow_origins=allowed_origins, allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"])

UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


@app.middleware("http")
async def check_origin(request: Request, call_next):
    """Protection CSRF : une requête qui modifie des données doit venir du site lui-même ou
    d'une origine déclarée (CORS_ORIGINS). Sans en-tête Origin (CLI, scripts), on laisse
    passer : le cookie SameSite=Lax n'est de toute façon pas envoyé par un autre site."""
    origin = request.headers.get("origin")
    if request.method in UNSAFE_METHODS and origin and origin != "null":
        host = request.headers.get("x-forwarded-host") or request.headers.get("host") or ""
        if urlsplit(origin).netloc != host and origin not in allowed_origins:
            return JSONResponse({"detail": "Origine non autorisée."}, status_code=403)
    return await call_next(request)


# ==================== ROUTES ====================

app.include_router(chat_router, prefix="/chat", tags=["chat"])
app.include_router(voice_router, prefix="/chat", tags=["voice"])  # WebSocket /chat/attempts/{id}/voice
app.include_router(attachment_router, tags=["attachments"])
app.include_router(evaluation_router, prefix="/evaluation", tags=["evaluation"])
app.include_router(user_router, prefix="/api/users", tags=["users"])
app.include_router(case_router, prefix="/api/cases", tags=["cases"])
app.include_router(admin_router, prefix="/admin", tags=["admin"])
app.include_router(authoring_router, prefix="/authoring", tags=["authoring"])
app.include_router(auth_router, prefix="/auth", tags=["auth"])


@app.get("/health", include_in_schema=False)
def health():
    """Supervision : l'API répond et la base est joignable."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception:  # noqa: BLE001
        logger.exception("Base de données injoignable")
        return JSONResponse({"status": "erreur", "database": False}, status_code=503)
    return {"status": "ok", "database": True}
