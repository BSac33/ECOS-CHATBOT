# authoring_routes.py
"""
Atelier de création de cas (enseignants) : /authoring

L'enseignant édite une fiche de cas structurée (case_sheet.CaseSheet). Le prompt du
patient, le contexte de l'évaluateur et la grille en sont compilés. Chaque
publication crée une version figée : une tentative garde la version qu'elle a jouée.

  GET    /authoring/cases                    mes cas (tous pour un administrateur)
  POST   /authoring/cases                    nouveau brouillon
  GET    /authoring/cases/{id}               fiche + aperçu compilé + vérifications + versions
  PUT    /authoring/cases/{id}/sheet         enregistrer la fiche
  POST   /authoring/cases/{id}/publish       publier (refusé s'il reste des erreurs)
  POST   /authoring/cases/{id}/test          tentative de test du brouillon (enseignant)
  GET    /authoring/reference/items          items EDN connus
  GET    /authoring/reference/situations     situations de départ (celles des items en premier)
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import List, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

import case_publishing
from auth import check_authorization
from case_sheet import CaseSheet, Issue, blocking, check_sheet, compile_case
from db import get_session
from models import (
    Attempts, CaseVersion, ChatRole, ClinicalCase, EDNItem, ItemSituationLink, Message,
    StartingSituation, StationType, User, UserRole,
)

router = APIRouter()
teacher = check_authorization(UserRole.teacher)


# ==================== SCHÉMAS ====================

class CaseSummary(BaseModel):
    id: int
    title: str
    status: str
    latest_version: Optional[int] = None
    errors: int
    warnings: int


class VersionOut(BaseModel):
    id: int
    version: int
    status: str
    created_at: str


class CompiledPreview(BaseModel):
    patient_prompt: str
    scenario_context: str
    student_instructions: str
    grid_items: List[dict]
    total_points: float


class CaseDetail(BaseModel):
    id: int
    status: str
    sheet: Optional[CaseSheet]
    legacy: bool                       # cas créé avant l'atelier (prompt libre, pas de fiche)
    preview: Optional[CompiledPreview]
    issues: List[Issue]
    versions: List[VersionOut]


class CreateCaseIn(BaseModel):
    title: Optional[str] = None


class PublishOut(BaseModel):
    version: VersionOut
    issues: List[Issue]


class TestAttemptOut(BaseModel):
    attempt_id: str
    version_id: int


# ==================== OUTILS ====================

def _own_case(session: Session, case_id: int, user: User) -> ClinicalCase:
    case = session.get(ClinicalCase, case_id)
    if not case:
        raise HTTPException(404, "Cas introuvable")
    if case.created_by != user.id and user.role != UserRole.admin:
        raise HTTPException(403, "Ce cas appartient à un autre enseignant")
    return case


def _version_out(v: CaseVersion) -> VersionOut:
    return VersionOut(id=v.id, version=v.version, status=v.status, created_at=v.created_at.isoformat())


def _sheet(case: ClinicalCase) -> Optional[CaseSheet]:
    return CaseSheet.model_validate(case.sheet) if case.sheet else None


def _preview(sheet: CaseSheet) -> CompiledPreview:
    c = compile_case(sheet)
    return CompiledPreview(patient_prompt=c["patient_prompt"], scenario_context=c["scenario_context"],
                           student_instructions=c["student_instructions"], grid_items=c["grid_items"],
                           total_points=c["total_points"])


def _detail(session: Session, case: ClinicalCase) -> CaseDetail:
    sheet = _sheet(case)
    return CaseDetail(
        id=case.id, status=case.status, sheet=sheet, legacy=sheet is None,
        preview=_preview(sheet) if sheet else None,
        issues=check_sheet(sheet) if sheet else [],
        versions=[_version_out(v) for v in case_publishing.versions(session, case.id)],
    )


# ==================== ROUTES ====================

@router.get("/cases", response_model=List[CaseSummary])
def list_cases(session: Session = Depends(get_session), user: User = Depends(teacher)):
    stmt = select(ClinicalCase)
    if user.role != UserRole.admin:
        stmt = stmt.where(ClinicalCase.created_by == user.id)
    out = []
    for case in session.exec(stmt.order_by(ClinicalCase.id.desc())).all():
        sheet = _sheet(case)
        issues = check_sheet(sheet) if sheet else []
        published = [v.version for v in case_publishing.versions(session, case.id) if v.status == "published"]
        out.append(CaseSummary(
            id=case.id, title=(sheet.station.title if sheet and sheet.station.title else case.title),
            status=case.status, latest_version=max(published, default=None),
            errors=sum(i.level == "erreur" for i in issues),
            warnings=sum(i.level == "attention" for i in issues),
        ))
    return out


@router.post("/cases", response_model=CaseDetail)
def create_case(payload: CreateCaseIn, session: Session = Depends(get_session), user: User = Depends(teacher)):
    sheet = CaseSheet()
    sheet.station.title = (payload.title or "").strip()
    case = ClinicalCase(
        # titre technique unique tant que le cas n'est pas publié
        title=f"Brouillon {datetime.now():%Y-%m-%d} {uuid4().hex[:6]}",
        created_by=user.id, status="draft", station_type=StationType.patient_interview,
        student_instructions="", scenario_context="", duration_seconds=sheet.station.duration_minutes * 60,
        sheet=sheet.model_dump(mode="json"),
    )
    session.add(case)
    session.commit()
    session.refresh(case)
    return _detail(session, case)


@router.get("/cases/{case_id}", response_model=CaseDetail)
def get_case(case_id: int, session: Session = Depends(get_session), user: User = Depends(teacher)):
    return _detail(session, _own_case(session, case_id, user))


@router.put("/cases/{case_id}/sheet", response_model=CaseDetail)
def save_sheet(case_id: int, sheet: CaseSheet, session: Session = Depends(get_session), user: User = Depends(teacher)):
    case = _own_case(session, case_id, user)
    case.sheet = sheet.model_dump(mode="json")
    session.add(case)
    session.commit()
    session.refresh(case)
    return _detail(session, case)


@router.post("/cases/{case_id}/publish", response_model=PublishOut)
def publish(case_id: int, session: Session = Depends(get_session), user: User = Depends(teacher)):
    case = _own_case(session, case_id, user)
    sheet = _sheet(case)
    if sheet is None:
        raise HTTPException(400, "Ce cas n'a pas de fiche : il a été créé avant l'atelier.")
    issues = check_sheet(sheet)
    if blocking(issues):
        raise HTTPException(422, {"message": "Corrigez les erreurs avant de publier.",
                                  "issues": [i.model_dump() for i in blocking(issues)]})
    title = sheet.station.title.strip()
    clash = session.exec(select(ClinicalCase).where(ClinicalCase.title == title, ClinicalCase.id != case.id)).first()
    if clash:
        raise HTTPException(409, f"Un autre cas porte déjà le titre « {title} ».")

    version = case_publishing.publish(session, case, sheet, user.id)
    session.commit()
    session.refresh(version)
    return PublishOut(version=_version_out(version), issues=issues)


@router.post("/cases/{case_id}/test", response_model=TestAttemptOut)
def test_draft(case_id: int, session: Session = Depends(get_session), user: User = Depends(teacher)):
    """Joue le brouillon tel quel (même avec des avertissements) dans une tentative de test."""
    case = _own_case(session, case_id, user)
    sheet = _sheet(case)
    if sheet is None:
        raise HTTPException(400, "Ce cas n'a pas de fiche.")
    if not sheet.facts:
        raise HTTPException(422, "Ajoutez au moins le motif de consultation avant de tester.")
    version = case_publishing.snapshot(session, case, sheet, "test", user.id)
    now = datetime.utcnow()
    attempt = Attempts(user_id=user.id, case_id=case.id, created_at=now, is_completed=False, is_test=True,
                       case_version_id=version.id, expires_at=now + timedelta(seconds=version.duration_seconds))
    session.add(attempt)
    session.flush()
    session.add(Message(attempt_id=attempt.id, role=ChatRole.system,
                        content=version.student_instructions or "Tentative de test", created_at=now))
    session.commit()
    return TestAttemptOut(attempt_id=str(attempt.id), version_id=version.id)


@router.get("/reference/items")
def reference_items(session: Session = Depends(get_session), user: User = Depends(teacher)):
    items = session.exec(select(EDNItem).order_by(EDNItem.number)).all()
    return [{"number": i.number, "title": i.title} for i in items]


@router.get("/reference/situations")
def reference_situations(items: str = "", session: Session = Depends(get_session), user: User = Depends(teacher)):
    """Situations de départ ; celles liées aux items donnés (ex. ?items=339,230) d'abord."""
    numbers = [int(x) for x in items.split(",") if x.strip().isdigit()]
    linked = set()
    if numbers:
        links = session.exec(select(ItemSituationLink).where(ItemSituationLink.item_number.in_(numbers))).all()
        linked = {l.situation_number for l in links}
    situations = session.exec(select(StartingSituation).order_by(StartingSituation.number)).all()
    out = [{"number": s.number, "title": s.title, "linked": s.number in linked} for s in situations]
    return sorted(out, key=lambda s: (not s["linked"], s["number"]))
