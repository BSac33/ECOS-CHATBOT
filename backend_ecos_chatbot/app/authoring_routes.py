# authoring_routes.py
"""
Atelier de création de cas (enseignants) : /authoring

L'enseignant édite une fiche de cas structurée (case_sheet.CaseSheet). Le prompt du
patient, le contexte de l'évaluateur et la grille en sont compilés. Chaque
publication crée une version figée : une tentative garde la version qu'elle a jouée.

Relecture par un pair : facultative. L'auteur peut mettre sa station « à relire » ; les
autres enseignants la voient alors dans leur liste, peuvent la lire, tester le patient et la
marquer comme relue (avec une remarque). Elle reste publiable à tout moment, relue ou non.

  GET    /authoring/cases                    mes cas (tous pour un administrateur)
  POST   /authoring/cases                    nouveau brouillon
  GET    /authoring/cases/{id}               fiche + aperçu compilé + vérifications + versions
  PUT    /authoring/cases/{id}/sheet         enregistrer la fiche
  POST   /authoring/cases/{id}/documents     ajouter un document de vignette (ECG, imagerie...)
  POST   /authoring/cases/{id}/publish       publier (refusé s'il reste des erreurs)
  POST   /authoring/cases/{id}/test          tentative de test du brouillon (auteur ou relecteur)
  POST   /authoring/cases/{id}/review/request demander une relecture (statut « à relire »)
  DELETE /authoring/cases/{id}/review         retirer le statut de relecture
  POST   /authoring/cases/{id}/review         marquer comme relue (autre enseignant ou administrateur)
  GET    /authoring/reference/items          items EDN connus
  GET    /authoring/reference/situations     situations de départ (celles des items en premier)
  POST   /authoring/cases/{id}/assist        propositions de l'assistant (« Générer »)
  GET    /authoring/corpus/search            extraits du corpus officiel (?q=...&items=339,230)
  GET    /authoring/corpus/objectives        objectifs hiérarchisés des items (?items=339)
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta
from typing import List, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import or_
from sqlmodel import Session, select

import authoring_assistant
import case_publishing
import chat_routes
import corpus
from auth import check_authorization
from case_sheet import CaseSheet, Issue, blocking, check_sheet, compile_case
from db import get_session
from models import (
    Attachment, Attempts, CaseVersion, ChatRole, ClinicalCase, EDNItem, ItemSituationLink, Message,
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
    owned: bool                        # False : station d'un collègue, à relire
    author: str
    review_status: Optional[str] = None


class ReviewOut(BaseModel):
    status: Optional[str] = None       # None | "a_relire" | "relue"
    requested_at: Optional[str] = None
    reviewer: Optional[str] = None
    reviewed_at: Optional[str] = None
    note: Optional[str] = None
    changed_since_review: bool = False


class ReviewIn(BaseModel):
    note: str = ""


class VersionOut(BaseModel):
    id: int
    version: int
    status: str
    created_at: str


class CompiledPreview(BaseModel):
    patient_prompt: Optional[str]          # None : station sans interlocuteur
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
    can_edit: bool                     # auteur ou administrateur ; sinon lecture (relecteur)
    can_review: bool
    author: str
    review: ReviewOut


class CreateCaseIn(BaseModel):
    title: Optional[str] = None


class PublishOut(BaseModel):
    version: VersionOut
    issues: List[Issue]


class TestAttemptOut(BaseModel):
    attempt_id: str
    version_id: int


# ==================== OUTILS ====================

def _can_edit(case: ClinicalCase, user: User) -> bool:
    return case.created_by == user.id or user.role == UserRole.admin


def _can_read(case: ClinicalCase, user: User) -> bool:
    return _can_edit(case, user) or case.review_status == "a_relire" or case.reviewed_by == user.id


def _can_review(case: ClinicalCase, user: User) -> bool:
    """Relecture par un pair : pas par l'auteur (sauf administrateur)."""
    return case.review_status == "a_relire" and (case.created_by != user.id or user.role == UserRole.admin)


def _own_case(session: Session, case_id: int, user: User) -> ClinicalCase:
    case = session.get(ClinicalCase, case_id)
    if not case:
        raise HTTPException(404, "Cas introuvable")
    if not _can_edit(case, user):
        raise HTTPException(403, "Ce cas appartient à un autre enseignant")
    return case


def _readable_case(session: Session, case_id: int, user: User) -> ClinicalCase:
    case = session.get(ClinicalCase, case_id)
    if not case:
        raise HTTPException(404, "Cas introuvable")
    if not _can_read(case, user):
        raise HTTPException(403, "Ce cas appartient à un autre enseignant")
    return case


def _sheet_hash(sheet: Optional[dict]) -> Optional[str]:
    if sheet is None:
        return None
    return hashlib.sha256(json.dumps(sheet, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16]


def _name(session: Session, user_id: Optional[int]) -> Optional[str]:
    u = session.get(User, user_id) if user_id else None
    return (u.full_name or u.username) if u else None


def _review(session: Session, case: ClinicalCase) -> ReviewOut:
    return ReviewOut(
        status=case.review_status,
        requested_at=case.review_requested_at.isoformat() if case.review_requested_at else None,
        reviewer=_name(session, case.reviewed_by),
        reviewed_at=case.reviewed_at.isoformat() if case.reviewed_at else None,
        note=case.review_note,
        changed_since_review=case.review_status == "relue" and _sheet_hash(case.sheet) != case.reviewed_sheet_hash,
    )


def _version_out(v: CaseVersion) -> VersionOut:
    return VersionOut(id=v.id, version=v.version, status=v.status, created_at=v.created_at.isoformat())


def _sheet(case: ClinicalCase) -> Optional[CaseSheet]:
    return CaseSheet.model_validate(case.sheet) if case.sheet else None


def _preview(sheet: CaseSheet) -> CompiledPreview:
    c = compile_case(sheet)
    return CompiledPreview(patient_prompt=c["patient_prompt"], scenario_context=c["scenario_context"],
                           student_instructions=c["student_instructions"], grid_items=c["grid_items"],
                           total_points=c["total_points"])


def _detail(session: Session, case: ClinicalCase, user: User) -> CaseDetail:
    sheet = _sheet(case)
    return CaseDetail(
        id=case.id, status=case.status, sheet=sheet, legacy=sheet is None,
        preview=_preview(sheet) if sheet else None,
        issues=check_sheet(sheet) if sheet else [],
        versions=[_version_out(v) for v in case_publishing.versions(session, case.id)],
        can_edit=_can_edit(case, user), can_review=_can_review(case, user),
        author=_name(session, case.created_by) or "", review=_review(session, case),
    )


# ==================== ROUTES ====================

@router.get("/cases", response_model=List[CaseSummary])
def list_cases(session: Session = Depends(get_session), user: User = Depends(teacher)):
    stmt = select(ClinicalCase)
    if user.role != UserRole.admin:
        # Mes stations + celles des collègues qui demandent une relecture
        stmt = stmt.where(or_(ClinicalCase.created_by == user.id, ClinicalCase.review_status == "a_relire"))
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
            owned=_can_edit(case, user), author=_name(session, case.created_by) or "",
            review_status=case.review_status,
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
    return _detail(session, case, user)


@router.get("/cases/{case_id}", response_model=CaseDetail)
def get_case(case_id: int, session: Session = Depends(get_session), user: User = Depends(teacher)):
    return _detail(session, _readable_case(session, case_id, user), user)


@router.put("/cases/{case_id}/sheet", response_model=CaseDetail)
def save_sheet(case_id: int, sheet: CaseSheet, session: Session = Depends(get_session), user: User = Depends(teacher)):
    case = _own_case(session, case_id, user)
    case.sheet = sheet.model_dump(mode="json")
    session.add(case)
    session.commit()
    session.refresh(case)
    return _detail(session, case, user)


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
    """Joue le brouillon tel quel (même avec des avertissements) dans une tentative de test.
    Ouvert à l'auteur et aux relecteurs."""
    case = _readable_case(session, case_id, user)
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
    chat_routes.add_start_messages(session, attempt, version, case)
    session.commit()
    return TestAttemptOut(attempt_id=str(attempt.id), version_id=version.id)


@router.get("/reference/items")
def reference_items(session: Session = Depends(get_session), user: User = Depends(teacher)):
    items = session.exec(select(EDNItem).order_by(EDNItem.number)).all()
    return [{"number": i.number, "title": i.title} for i in items]


@router.get("/reference/situations")
def reference_situations(items: str = "", session: Session = Depends(get_session), user: User = Depends(teacher)):
    """Situations de départ ; celles liées aux items donnés (ex. ?items=339,230) d'abord."""
    numbers = _numbers(items)
    linked = set()
    if numbers:
        links = session.exec(select(ItemSituationLink).where(ItemSituationLink.item_number.in_(numbers))).all()
        linked = {l.situation_number for l in links}
    situations = session.exec(select(StartingSituation).order_by(StartingSituation.number)).all()
    out = [{"number": s.number, "title": s.title, "linked": s.number in linked} for s in situations]
    return sorted(out, key=lambda s: (not s["linked"], s["number"]))


def _numbers(items: str) -> List[int]:
    return [int(x) for x in items.split(",") if x.strip().isdigit()]


class CorpusHitOut(BaseModel):
    chunk_id: int
    label: str
    item_number: Optional[int]
    section: str
    rank: Optional[str]
    kind: str
    text: str
    url: str
    score: float


@router.get("/corpus/search", response_model=List[CorpusHitOut])
def corpus_search(q: str, items: str = "", kinds: str = "", limit: int = 6,
                  session: Session = Depends(get_session), user: User = Depends(teacher)):
    hits = corpus.search_corpus(session, q, items=_numbers(items),
                                kinds=[k for k in kinds.split(",") if k] or None, limit=min(limit, 20))
    return [CorpusHitOut(chunk_id=h.chunk_id, label=h.label, item_number=h.item_number, section=h.section,
                         rank=h.rank, kind=h.kind, text=h.text, url=h.url, score=h.score) for h in hits]


@router.get("/corpus/objectives")
def corpus_objectives(items: str, session: Session = Depends(get_session), user: User = Depends(teacher)):
    return [{"chunk_id": o.id, "item_number": o.item_number, "rank": o.rank, "rubric": o.section,
             "text": o.text, "url": o.url} for o in corpus.objectives(session, _numbers(items))]


class AssistIn(BaseModel):
    task: authoring_assistant.Task
    instructions: str = ""
    sheet: Optional[CaseSheet] = None      # fiche en cours d'édition (non enregistrée)


@router.post("/cases/{case_id}/assist", response_model=authoring_assistant.Proposal)
async def assist(case_id: int, payload: AssistIn, session: Session = Depends(get_session), user: User = Depends(teacher)):
    """Propositions à relire ; la fiche n'est pas modifiée (l'éditeur ajoute ce que l'enseignant accepte)."""
    case = _own_case(session, case_id, user)
    sheet = payload.sheet or _sheet(case)
    if sheet is None:
        raise HTTPException(400, "Ce cas n'a pas de fiche.")
    try:
        return await authoring_assistant.assist(sheet, payload.task, session=session, instructions=payload.instructions)
    except authoring_assistant.AssistantInputError as exc:
        raise HTTPException(422, str(exc))
    except authoring_assistant.AssistantError as exc:
        raise HTTPException(502, str(exc))


# ==================== RELECTURE (facultative, ne bloque pas la publication) ====================

@router.post("/cases/{case_id}/review/request", response_model=CaseDetail)
def request_review(case_id: int, session: Session = Depends(get_session), user: User = Depends(teacher)):
    case = _own_case(session, case_id, user)
    case.review_status = "a_relire"
    case.review_requested_at = datetime.now()
    case.reviewed_by = case.reviewed_at = case.review_note = case.reviewed_sheet_hash = None
    session.add(case)
    session.commit()
    session.refresh(case)
    return _detail(session, case, user)


@router.delete("/cases/{case_id}/review", response_model=CaseDetail)
def clear_review(case_id: int, session: Session = Depends(get_session), user: User = Depends(teacher)):
    case = _own_case(session, case_id, user)
    case.review_status = case.review_requested_at = None
    case.reviewed_by = case.reviewed_at = case.review_note = case.reviewed_sheet_hash = None
    session.add(case)
    session.commit()
    session.refresh(case)
    return _detail(session, case, user)


@router.post("/cases/{case_id}/review", response_model=CaseDetail)
def mark_reviewed(case_id: int, payload: ReviewIn, session: Session = Depends(get_session), user: User = Depends(teacher)):
    case = _readable_case(session, case_id, user)
    if case.review_status != "a_relire":
        raise HTTPException(409, "Aucune relecture n'est demandée pour cette station.")
    if not _can_review(case, user):
        raise HTTPException(403, "La relecture doit être faite par un autre enseignant.")
    case.review_status = "relue"
    case.reviewed_by = user.id
    case.reviewed_at = datetime.now()
    case.review_note = payload.note.strip() or None
    case.reviewed_sheet_hash = _sheet_hash(case.sheet)
    session.add(case)
    session.commit()
    session.refresh(case)
    return _detail(session, case, user)


# ==================== DOCUMENTS DE LA VIGNETTE ====================

DOCUMENT_TYPES = {"image/png", "image/jpeg", "image/webp", "image/gif", "application/pdf"}
MAX_DOCUMENT_BYTES = 15_000_000


class DocumentOut(BaseModel):
    attachment_id: str
    filename: str
    mime_type: str
    url: str


@router.post("/cases/{case_id}/documents", response_model=DocumentOut)
async def upload_document(case_id: int, file: UploadFile = File(...), label: str = Form(""),
                          session: Session = Depends(get_session), user: User = Depends(teacher)):
    """Fichier d'un document de la vignette ; la fiche le référence ensuite (station.documents)."""
    import mimetypes
    from pathlib import Path

    from storage import storage

    case = _own_case(session, case_id, user)
    data = await file.read()
    mime = file.content_type or mimetypes.guess_type(file.filename or "")[0] or ""
    if mime not in DOCUMENT_TYPES:
        raise HTTPException(415, "Formats acceptés : image (PNG, JPEG, WebP, GIF) ou PDF.")
    if len(data) > MAX_DOCUMENT_BYTES:
        raise HTTPException(413, "Fichier trop volumineux (15 Mo maximum).")
    name = Path(file.filename or "document").name
    path = f"authoring/{case.id}/{uuid4().hex}{Path(name).suffix.lower()}"
    url = await storage.save_file(data, path)
    attachment = Attachment(case_id=case.id, filename=name, stored_filename=Path(path).name,
                            display_name=label.strip() or name, description=label.strip() or None,
                            kind="image" if mime.startswith("image/") else "document", mime_type=mime,
                            size_bytes=len(data), file_path=path, file_url=url)
    session.add(attachment)
    session.commit()
    session.refresh(attachment)
    return DocumentOut(attachment_id=str(attachment.id), filename=name, mime_type=mime,
                       url=f"/attachments/download/{attachment.id}")
