from tabnanny import check
from xml.sax import handler
from fastapi import FastAPI, APIRouter, Depends
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from httpx import get
from sqlmodel import Field, Relationship, Session, SQLModel, create_engine
from typing import Annotated, Optional, List
from enum import Enum
from db import get_session
import os
import dotenv
from models import ClinicalCase, ClinicalCaseCreateIn, EDNItem, DisciplineItem, CaseEdnLink, CaseDisciplineLink, EdnDisciplineLink, User, UserRole
from chat_routes import router as chat_router
from attachment_routes import router as attachment_router
from evaluation_routes import router as evaluation_router
from user_routes import router as user_router
from admin_routes import router as admin_router
from case_routes import router as case_router
from auth import check_authorization, router as auth_router
from pathlib import Path
import logging

# Charger les variables d'environnement depuis fastapi.env
dotenv.load_dotenv("fastapi.env")

app = FastAPI(
    title="ECOS Chatbot API",
    )

# Configuration CORS pour le frontend
# IMPORTANT : avec credentials=True (cookies HttpOnly), on ne peut PAS utiliser allow_origins=["*"]
# Il faut spécifier les origines exactes autorisées
allowed_origins = os.getenv(
    "CORS_ORIGINS", 
    "http://localhost:3000,http://localhost:5173"
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,  # Origines autorisées (pas de wildcard avec credentials)
    allow_credentials=True,  # ESSENTIEL : permet l'envoi/réception de cookies HttpOnly
    allow_methods=["*"],  # Toutes les méthodes HTTP (GET, POST, PUT, DELETE, etc.)
    allow_headers=["*"],  # Tous les headers autorisés
    expose_headers=["*"],  # Headers exposés au frontend
)

# Configurer le logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
handler.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)  
logger.propagate = True

# Inclure les routers
app.include_router(chat_router, prefix="/chat", tags=["chat"])
app.include_router(attachment_router, tags=["attachments"])
app.include_router(evaluation_router, prefix="/evaluation", tags=["evaluation"])
app.include_router(user_router, prefix="/api/users", tags=["users"])
app.include_router(case_router, prefix="/api/cases", tags=["cases"])
app.include_router(admin_router, prefix="/admin", tags=["admin"])
app.include_router(auth_router, prefix="/auth", tags=["auth"])

# Servir les fichiers statiques (pour le stockage local)
storage_path = Path("storage")
if storage_path.exists():
    app.mount("/files", StaticFiles(directory="storage"), name="files")

    