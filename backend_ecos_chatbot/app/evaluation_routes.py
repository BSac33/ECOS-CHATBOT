"""
Routes pour l'évaluation des tentatives ECOS.

L'évaluateur ne parle JAMAIS avec l'étudiant pendant l'examen.
L'évaluation se fait après la fin de la station en analysant le transcript complet.
"""

import copy
import logging
from datetime import datetime
from typing import Annotated, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

import case_publishing
from auth import check_authorization
from db import get_session
from evaluation_service import (
    UNAVAILABLE_MESSAGE, EvaluationUnavailable, evaluate_attempt_with_llm, missing_parts, silent_evaluation,
)
from models import (
    Attempts, CaseVersion, ChatRole, ClinicalCase, EvaluationGrid, EvaluationItemResult, EvaluationOut,
    EvaluationResult, Message, User, UserRole,
)
from scoring import recompute_totals, score_evaluation

logger = logging.getLogger(__name__)


router = APIRouter()

INTERRUPTION_LABEL = "coupé par l'étudiant"


def _spoken_text(msg) -> str:
    return msg.spoken_content if msg.interrupted_by and msg.spoken_content is not None else msg.content


NO_INTERLOCUTOR_HEADER = ("[STATION SANS INTERLOCUTEUR] L'étudiant expose son raisonnement à voix haute "
                          "devant les examinateurs, qui n'interviennent pas.")


def build_evaluation_transcript(messages: list, no_interlocutor: bool = False,
                                professional: Optional[str] = None) -> tuple[str, int]:
    """Transcript soumis à l'évaluateur, et nombre de fois où l'étudiant a coupé la
    parole au patient. Une réplique coupée n'y figure que pour ce qui a été prononcé."""
    parts = []
    interruptions = 0
    spoken_mode = any(getattr(m, "modality", "text") == "voice" for m in messages)
    for msg in messages:
        # Filtrer les commandes CLI (/end, /finalize, etc.)
        if msg.content.startswith('/'):
            continue
        role = msg.role.value
        if role == "student":
            parts.append(f"ÉTUDIANT: {msg.content}")
        elif role == "patient" and professional:
            # Professionnel de santé simulé : même canal que le patient, autre rôle
            parts.append(f"PROFESSIONNEL DE SANTÉ ({professional}): {_spoken_text(msg)}")
        elif role == "patient":
            if msg.interrupted_by:
                interruptions += 1
                spoken = msg.spoken_content if msg.spoken_content is not None else msg.content
                parts.append(f"PATIENT ({INTERRUPTION_LABEL}): {spoken}")
            else:
                parts.append(f"PATIENT: {msg.content}")
        elif role == "examiner":
            # Résultats d'examen clinique / documents montrés à l'étudiant
            parts.append(f"EXAMINATEUR: {msg.content}")
        # On ignore les messages system
    transcript = "\n\n".join(parts)
    if no_interlocutor:
        return f"{NO_INTERLOCUTOR_HEADER}\n\n{transcript}", 0
    if spoken_mode:
        header = (f"[COMMUNICATION ORALE] L'étudiant a coupé la parole au patient {interruptions} fois"
                  if interruptions else
                  "[COMMUNICATION ORALE] L'étudiant n'a jamais coupé la parole au patient")
        transcript = f"{header}\n\n{transcript}"
    return transcript, interruptions


# ==================== CORRECTION ====================

def _grid_and_context(session: Session, attempt: Attempts, case: ClinicalCase) -> tuple[dict, str, dict]:
    """Grille et contexte de la version du cas qui a été jouée (une republication ne change
    pas la correction d'une tentative passée)."""
    version = session.get(CaseVersion, attempt.case_version_id) if attempt.case_version_id else None
    info = case_publishing.runtime(version) or {}
    if version is not None:
        grid = {"items": version.grid_items, "version": float(version.version),
                "total_points": version.total_points,
                # Échelles d'attitude et évaluation globale (format des ECOS nationaux)
                "scales": info.get("scales") or [],
                "global_rating": bool(info.get("global_rating")),
                "attitude_weight": info.get("attitude_weight", 0.25)}
        title, instructions, scenario = version.title, version.student_instructions, version.scenario_context
    else:
        eval_grid = session.exec(select(EvaluationGrid).where(
            EvaluationGrid.case_id == case.id, EvaluationGrid.is_active == True)).first()  # noqa: E712
        if not eval_grid:
            raise HTTPException(404, f"Aucune grille d'évaluation active pour le cas « {case.title} »")
        grid = {"items": eval_grid.items, "version": eval_grid.version, "total_points": eval_grid.total_points}
        title, instructions, scenario = case.title, case.student_instructions, case.scenario_context
    context = (f"Titre : {title}\nType de station : {case.station_type.value}\n\n"
               f"Consignes pour l'étudiant :\n{instructions}\n\nContexte du scénario :\n{scenario}\n")
    return grid, context, info


def _student_text(messages: list) -> str:
    return "\n".join(m.content for m in messages
                     if m.role == ChatRole.student and not m.content.startswith("/"))


def _save(session: Session, attempt_id: UUID, case_id: int, user_id: int, result: dict) -> dict:
    """Enregistre la correction ; si une autre requête l'a enregistrée entre-temps
    (double clic), renvoie celle-là plutôt qu'une erreur."""
    evaluation = result["evaluation"]
    record = EvaluationResult(attempt_id=attempt_id, case_id=case_id, user_id=user_id, evaluation_data=result,
                              points_obtained=evaluation["score_20"], points_possible=20.0)
    session.add(record)
    try:
        session.flush()
    except IntegrityError:
        session.rollback()
        existing = session.exec(select(EvaluationResult).where(EvaluationResult.attempt_id == attempt_id)).first()
        if existing is None:
            raise
        return existing.evaluation_data
    for item in evaluation.get("items", []):
        session.add(EvaluationItemResult(
            evaluation_result_id=record.id, attempt_id=attempt_id, case_id=case_id, user_id=user_id,
            edn_code=item.get("edn_code") or "", item_name=item.get("criterion", ""),
            points_obtained=item.get("points_awarded", 0.0), points_possible=item.get("points_possible", 0.0),
            justification=item.get("justification", ""), evaluated_at=datetime.now()))
    session.commit()
    return result


def run_evaluation(session: Session, attempt: Attempts) -> dict:
    """Correction complète d'une tentative terminée : transcription, appel au LLM (connexion à la
    base rendue pendant l'appel), vérification, note, enregistrement. HTTPException 503 si échec."""
    case = session.get(ClinicalCase, attempt.case_id)
    if not case:
        raise HTTPException(404, "Cas clinique introuvable")
    grid, case_context, info = _grid_and_context(session, attempt, case)
    messages = session.exec(select(Message).where(Message.attempt_id == attempt.id)
                            .order_by(Message.created_at)).all()
    transcript, _ = build_evaluation_transcript(
        messages, no_interlocutor=info.get("interlocutor") == "aucun",
        professional=info.get("interlocutor_label") if info.get("interlocutor") == "professionnel" else None)
    student_text = _student_text(messages)
    attempt_id, case_id, owner_id = attempt.id, case.id, attempt.user_id
    # Fin de la transaction de lecture : la connexion retourne au pool pendant l'appel au modèle
    session.rollback()

    if not student_text.strip():
        output = silent_evaluation(grid)
    else:
        try:
            output = evaluate_attempt_with_llm(transcript=transcript, evaluation_grid=grid, case_context=case_context)
        except EvaluationUnavailable as exc:
            logger.warning("Correction indisponible pour la tentative %s : %s", attempt_id, exc)
            raise HTTPException(503, UNAVAILABLE_MESSAGE)
        if missing_parts(output, grid):
            raise HTTPException(503, UNAVAILABLE_MESSAGE)
    result = score_evaluation(output, grid, student_text)
    return _save(session, attempt_id, case_id, owner_id, result)


@router.post("/attempts/{attempt_id}/evaluate", response_model=EvaluationOut)
def evaluate_attempt(attempt_id: UUID, session: Annotated[Session, Depends(get_session)],
                     user: Annotated[User, Depends(check_authorization(UserRole.student))]):
    """Correction d'une tentative terminée, après la station (l'évaluateur n'intervient jamais
    pendant). Mise en cache : un second appel renvoie la même correction. 503 si la correction
    n'a pas abouti (rien n'est enregistré : l'étudiant peut relancer)."""
    attempt = session.get(Attempts, attempt_id)
    if not attempt or attempt.user_id != user.id:
        raise HTTPException(404, "Tentative non trouvée")
    if not attempt.is_completed:
        raise HTTPException(400, "Terminez la station avant de demander la correction.")
    existing = session.exec(select(EvaluationResult).where(EvaluationResult.attempt_id == attempt_id)).first()
    if existing:
        return existing.evaluation_data
    return run_evaluation(session, attempt)


# ==================== RELECTURE PAR UN ENSEIGNANT ====================

def can_review(case: Optional[ClinicalCase], user: User) -> bool:
    return case is not None and (user.role == UserRole.admin
                                 or (user.role == UserRole.teacher and case.created_by == user.id))


def _reviewable_attempt(session: Session, attempt_id: UUID, user: User) -> tuple[Attempts, ClinicalCase]:
    attempt = session.get(Attempts, attempt_id)
    case = session.get(ClinicalCase, attempt.case_id) if attempt else None
    if not attempt or not can_review(case, user):
        raise HTTPException(404, "Tentative non trouvée")
    return attempt, case


class ItemOverride(BaseModel):
    points_awarded: float = Field(ge=0)
    justification: Optional[str] = Field(default=None, max_length=4000)


@router.get("/attempts/{attempt_id}/review")
def review_attempt(attempt_id: UUID, session: Annotated[Session, Depends(get_session)],
                   user: Annotated[User, Depends(check_authorization(UserRole.teacher))]):
    """Transcription et correction d'une tentative, pour l'auteur de la station (ou un admin)."""
    attempt, case = _reviewable_attempt(session, attempt_id, user)
    student = session.get(User, attempt.user_id)
    existing = session.exec(select(EvaluationResult).where(EvaluationResult.attempt_id == attempt_id)).first()
    return {
        "attempt_id": str(attempt.id), "case_id": case.id, "case_title": case.title,
        "username": student.username if student else None, "full_name": student.full_name if student else None,
        "completed_at": attempt.completed_at.isoformat() if attempt.completed_at else None,
        "transcript": _transcript_rows(session, attempt.id),
        "evaluation": existing.evaluation_data["evaluation"] if existing else None,
    }


@router.patch("/attempts/{attempt_id}/items/{item_id}", response_model=EvaluationOut)
def override_item(attempt_id: UUID, item_id: str, payload: ItemOverride,
                  session: Annotated[Session, Depends(get_session)],
                  user: Annotated[User, Depends(check_authorization(UserRole.teacher))]):
    """Modification d'un item par l'enseignant : points, justification ; note recalculée, tracée."""
    _reviewable_attempt(session, attempt_id, user)
    record = session.exec(select(EvaluationResult).where(EvaluationResult.attempt_id == attempt_id)).first()
    if record is None:
        raise HTTPException(404, "Pas encore de correction pour cette tentative")
    data = copy.deepcopy(record.evaluation_data)
    evaluation = data["evaluation"]
    item = next((i for i in evaluation.get("items") or [] if str(i.get("item_id")) == item_id), None)
    if item is None:
        raise HTTPException(404, "Item introuvable dans la grille")
    if payload.points_awarded > float(item["points_possible"]):
        raise HTTPException(422, f"Au plus {item['points_possible']:g} point(s) pour cet item")
    item["points_awarded"] = payload.points_awarded
    if payload.justification is not None:
        item["justification"] = payload.justification.strip() or item["justification"]
    item["overridden"] = True
    recompute_totals(evaluation)
    evaluation["reviewed_by"] = user.full_name or user.username
    evaluation["reviewed_at"] = datetime.now().isoformat(timespec="seconds")
    record.evaluation_data = data
    record.points_obtained = evaluation["score_20"]
    record.evaluated_at = datetime.now()
    row = session.exec(select(EvaluationItemResult).where(
        EvaluationItemResult.evaluation_result_id == record.id,
        EvaluationItemResult.item_name == item.get("criterion", ""))).first()
    if row is not None:
        row.points_obtained = item["points_awarded"]
        row.justification = item["justification"]
        session.add(row)
    session.add(record)
    session.commit()
    return data


@router.post("/attempts/{attempt_id}/reevaluate", response_model=EvaluationOut)
def reevaluate_attempt(attempt_id: UUID, session: Annotated[Session, Depends(get_session)],
                       user: Annotated[User, Depends(check_authorization(UserRole.teacher))]):
    """Nouvelle correction automatique (remplace l'ancienne, y compris les modifications)."""
    attempt, _ = _reviewable_attempt(session, attempt_id, user)
    if not attempt.is_completed:
        raise HTTPException(400, "La tentative n'est pas terminée.")
    record = session.exec(select(EvaluationResult).where(EvaluationResult.attempt_id == attempt_id)).first()
    if record is not None:
        for row in session.exec(select(EvaluationItemResult).where(
                EvaluationItemResult.evaluation_result_id == record.id)).all():
            session.delete(row)
        session.delete(record)
        session.commit()
    attempt = session.get(Attempts, attempt_id)
    return run_evaluation(session, attempt)


def _transcript_rows(session: Session, attempt_id: UUID) -> list[dict]:
    messages = session.exec(select(Message).where(Message.attempt_id == attempt_id)
                            .order_by(Message.created_at)).all()
    return [{"id": str(m.id), "role": m.role.value, "content": m.content, "modality": m.modality,
             "interrupted_by": m.interrupted_by, "spoken_content": m.spoken_content,
             "timestamp": m.created_at.isoformat() if m.created_at else None}
            for m in messages if m.role.value != "system"]


@router.get("/attempts/{attempt_id}/transcript")
def get_transcript(attempt_id: UUID, session: Session = Depends(get_session), user: User = Depends(check_authorization())):
    """
    Récupère le transcript complet d'une tentative.
    Utile pour visualiser ce qui sera évalué.
    """
    user_id = user.id
    
    attempt = session.get(Attempts, attempt_id)
    if not attempt or attempt.user_id != user_id:
        raise HTTPException(404, "Tentative non trouvée")
    
    transcript = _transcript_rows(session, attempt_id)
    interruptions = [{"message_id": str(r["id"]), "reason": r["interrupted_by"],
                      "spoken_content": r["spoken_content"], "full_reply": r["content"]}
                     for r in transcript if r["interrupted_by"]]
    return {
        "attempt_id": attempt_id,
        "case_id": attempt.case_id,
        "is_completed": attempt.is_completed,
        "transcript": transcript,
        # En ECOS, on ne coupe pas la parole au patient
        "interruptions": interruptions,
    }


@router.get("/attempts/{attempt_id}/teaching")
def get_teaching(attempt_id: UUID, session: Session = Depends(get_session), user: User = Depends(check_authorization())):
    """Contenu pédagogique de la station (objectifs, éléments clés, script, commentaires).
    Seulement après la fin de la tentative : il ne doit pas aider pendant la station."""
    attempt = session.get(Attempts, attempt_id)
    if not attempt or attempt.user_id != user.id:
        raise HTTPException(404, "Tentative non trouvée")
    if not attempt.is_completed:
        raise HTTPException(400, "Disponible après la fin de la station.")
    version = session.get(CaseVersion, attempt.case_version_id) if attempt.case_version_id else None
    sheet = (version.sheet or {}) if version else {}
    teaching = (sheet.get("correction") or {}).get("teaching") or {}
    station = sheet.get("station") or {}
    return {
        "title": version.title if version else None,
        "source": station.get("source") or None,
        "objectives": teaching.get("objectives") or [],
        "key_points": teaching.get("key_points") or [],
        "model_script": teaching.get("model_script") or "",
        "comments": teaching.get("comments") or "",
    }
