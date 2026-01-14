from fastapi import FastAPI, APIRouter, Depends
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from httpx import get
from sqlmodel import Field, Relationship, Session, SQLModel, create_engine
from typing import Optional, List
from enum import Enum
from db import get_session
import os
import dotenv
from models import ClinicalCase, EDNItem, DisciplineItem, CaseEdnLink, CaseDisciplineLink, EdnDisciplineLink, User
from chat_routes import router as chat_router
from attachment_routes import router as attachment_router
from evaluation_routes import router as evaluation_router
from user_routes import router as user_router
from admin_routes import router as admin_router
from auth import router as auth_router
from pathlib import Path

app = FastAPI(title="ECOS Chatbot API")

# Inclure les routers
app.include_router(chat_router, prefix="/chat", tags=["chat"])
app.include_router(attachment_router, tags=["attachments"])
app.include_router(evaluation_router, prefix="/evaluation", tags=["evaluation"])
app.include_router(user_router, prefix="/api", tags=["users"])
app.include_router(admin_router, prefix="/admin", tags=["admin"])
app.include_router(auth_router, prefix="/auth", tags=["auth"])

# Servir les fichiers statiques (pour le stockage local)
storage_path = Path("storage")
if storage_path.exists():
    app.mount("/files", StaticFiles(directory="storage"), name="files")
    
##============================ ROUTES ============================##
    
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///database.db")
print(f"Using database URL: {DATABASE_URL}")
    
engine = create_engine(DATABASE_URL)

@app.get("/")
async def root():
    return {"message": "Hello World"}

@app.get("/cases/{case_id}")
async def get_case(case_id: int):
    """Récupère un cas publié (pour les étudiants)"""
    with Session(engine) as session:
        case = session.get(ClinicalCase, case_id)
        if case and case.status == "published":
            return case
        return {"error": "Case not found"}
    
@app.get("/cases")
async def list_published_cases():
    """Liste tous les cas publiés (pour les étudiants)"""
    from sqlmodel import select
    with Session(engine) as session:
        stmt = select(ClinicalCase).where(ClinicalCase.status == "published")
        cases = session.exec(stmt).all()
        return [
            {
                "id": case.id,
                "title": case.title,
                "station_type": case.station_type.value,
                "duration_seconds": case.duration_seconds
            }
            for case in cases
        ]
    
@app.post("/case")
async def create_case(case: ClinicalCase):
    with Session(engine) as session:
        session.add(case)
        session.commit()
        session.refresh(case)
        return HTMLResponse(content=f"Case {case.id} created", status_code=201)
    
@app.post("/ednitem")
async def create_edn_item(edn_item: EDNItem):
    with Session(engine) as session:
        session.add(edn_item)
        session.commit()
        session.refresh(edn_item)
        return HTMLResponse(content=f"EDN Item {edn_item.number} created", status_code=201)
    
@app.post("/user")
async def create_user(user: User, session: Session = Depends(get_session)):
    session.add(user)
    session.commit()
    session.refresh(user)
    return HTMLResponse(content=f"User {user.username} created", status_code=201)

    
