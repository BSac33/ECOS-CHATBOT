"""
Routes pour gérer les données utilisateur et statistiques.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select, func
from datetime import datetime
from typing import Optional, List
from uuid import UUID

from db import get_session
from models import (
    User, Attempts, ClinicalCase, Message, EvaluationGrid,
    StationType, ChatRole
)
from pydantic import BaseModel


router = APIRouter()


# Modèles de réponse pour les statistiques
class AttemptSummary(BaseModel):
    """Résumé d'une tentative pour l'affichage liste"""
    id: str  # UUID
    case_id: int
    case_title: str
    station_type: str
    created_at: str
    completed_at: Optional[str] = None
    is_completed: bool
    message_count: int
    duration_seconds: Optional[int] = None


class UserStats(BaseModel):
    """Statistiques globales d'un utilisateur"""
    total_attempts: int
    completed_attempts: int
    in_progress_attempts: int
    total_messages: int
    cases_attempted: List[int]  # Liste des case_id uniques
    favorite_discipline: Optional[str] = None


class UserAttemptsResponse(BaseModel):
    """Réponse complète avec tentatives et stats"""
    attempts: List[AttemptSummary]
    stats: UserStats


# Helper pour récupérer l'utilisateur actuel (à remplacer par vraie auth)
def get_current_user_id() -> int:
    """TODO: Remplacer par vraie authentification JWT"""
    return 45


@router.get("/users/me/attempts", response_model=UserAttemptsResponse)
def get_user_attempts(
    completed: Optional[bool] = Query(None, description="Filtrer par statut (true=complétées, false=en cours, null=toutes)"),
    case_id: Optional[int] = Query(None, description="Filtrer par cas clinique"),
    station_type: Optional[StationType] = Query(None, description="Filtrer par type de station"),
    limit: int = Query(50, ge=1, le=200, description="Nombre maximum de résultats"),
    offset: int = Query(0, ge=0, description="Décalage pour pagination"),
    session: Session = Depends(get_session),
):
    """
    Récupère toutes les tentatives d'un utilisateur avec filtres et statistiques.
    
    Utilisé pour :
    - Afficher l'historique des ECOS
    - Statistiques du dashboard
    - Reprise de tentatives en cours
    """
    user_id = get_current_user_id()
    
    # Construire la requête de base
    stmt = (
        select(
            Attempts,
            ClinicalCase.title,
            ClinicalCase.station_type,
            func.count(Message.id).label("message_count")
        )
        .join(ClinicalCase, Attempts.case_id == ClinicalCase.id)
        .outerjoin(Message, Message.attempt_id == Attempts.id)
        .where(Attempts.user_id == user_id)
        .group_by(Attempts.id, ClinicalCase.title, ClinicalCase.station_type)
    )
    
    # Appliquer les filtres
    if completed is not None:
        stmt = stmt.where(Attempts.is_completed == completed)
    
    if case_id is not None:
        stmt = stmt.where(Attempts.case_id == case_id)
    
    if station_type is not None:
        stmt = stmt.where(ClinicalCase.station_type == station_type)
    
    # Ordre et pagination
    stmt = stmt.order_by(Attempts.created_at.desc()).offset(offset).limit(limit)
    
    results = session.exec(stmt).all()
    
    # Construire la liste des tentatives
    attempts_list = []
    for attempt, case_title, station_type_val, msg_count in results:
        # Calculer la durée si complétée
        duration = None
        if attempt.is_completed and attempt.completed_at and attempt.created_at:
            duration = int((attempt.completed_at - attempt.created_at).total_seconds())
        
        attempts_list.append(AttemptSummary(
            id=str(attempt.id),
            case_id=attempt.case_id,
            case_title=case_title,
            station_type=station_type_val.value,
            created_at=attempt.created_at.isoformat() if attempt.created_at else "",
            completed_at=attempt.completed_at.isoformat() if attempt.completed_at else None,
            is_completed=attempt.is_completed,
            message_count=msg_count,
            duration_seconds=duration,
        ))
    
    # Calculer les statistiques globales (sans filtres)
    stats_stmt = (
        select(
            func.count(Attempts.id).label("total"),
            func.count(Attempts.id).filter(Attempts.is_completed == True).label("completed"),
            func.count(Attempts.id).filter(Attempts.is_completed == False).label("in_progress"),
        )
        .where(Attempts.user_id == user_id)
    )
    
    stats_result = session.exec(stats_stmt).first()
    total_attempts = stats_result[0] if stats_result else 0
    completed_attempts = stats_result[1] if stats_result else 0
    in_progress_attempts = stats_result[2] if stats_result else 0
    
    # Nombre total de messages
    msg_stmt = (
        select(func.count(Message.id))
        .join(Attempts, Message.attempt_id == Attempts.id)
        .where(Attempts.user_id == user_id)
    )
    total_messages = session.exec(msg_stmt).first() or 0
    
    # Cases uniques tentées
    cases_stmt = (
        select(Attempts.case_id)
        .where(Attempts.user_id == user_id)
        .distinct()
    )
    cases_attempted = [case_id for case_id in session.exec(cases_stmt).all()]
    
    # Discipline préférée (celle avec le plus de tentatives)
    # TODO: Implémenter quand on a les liens CaseDiscipline
    favorite_discipline = None
    
    stats = UserStats(
        total_attempts=total_attempts,
        completed_attempts=completed_attempts,
        in_progress_attempts=in_progress_attempts,
        total_messages=total_messages,
        cases_attempted=cases_attempted,
        favorite_discipline=favorite_discipline,
    )
    
    return UserAttemptsResponse(attempts=attempts_list, stats=stats)


@router.get("/users/me/attempts/{attempt_id}", response_model=AttemptSummary)
def get_user_attempt_detail(
    attempt_id: UUID,
    session: Session = Depends(get_session),
):
    """
    Récupère les détails d'une tentative spécifique.
    Vérifie que l'attempt appartient bien à l'utilisateur.
    """
    user_id = get_current_user_id()
    
    stmt = (
        select(
            Attempts,
            ClinicalCase.title,
            ClinicalCase.station_type,
            func.count(Message.id).label("message_count")
        )
        .join(ClinicalCase, Attempts.case_id == ClinicalCase.id)
        .outerjoin(Message, Message.attempt_id == Attempts.id)
        .where(Attempts.id == attempt_id, Attempts.user_id == user_id)
        .group_by(Attempts.id, ClinicalCase.title, ClinicalCase.station_type)
    )
    
    result = session.exec(stmt).first()
    
    if not result:
        raise HTTPException(404, "Attempt not found or access denied")
    
    attempt, case_title, station_type_val, msg_count = result
    
    duration = None
    if attempt.is_completed and attempt.completed_at and attempt.created_at:
        duration = int((attempt.completed_at - attempt.created_at).total_seconds())
    
    return AttemptSummary(
        id=str(attempt.id),
        case_id=attempt.case_id,
        case_title=case_title,
        station_type=station_type_val.value,
        created_at=attempt.created_at.isoformat() if attempt.created_at else "",
        completed_at=attempt.completed_at.isoformat() if attempt.completed_at else None,
        is_completed=attempt.is_completed,
        message_count=msg_count,
        duration_seconds=duration,
    )


@router.delete("/users/me/attempts/{attempt_id}")
def delete_user_attempt(
    attempt_id: UUID,
    session: Session = Depends(get_session),
):
    """
    Supprime une tentative de l'utilisateur.
    Supprime également tous les messages associés (cascade).
    """
    user_id = get_current_user_id()
    
    attempt = session.get(Attempts, attempt_id)
    
    if not attempt:
        raise HTTPException(404, "Attempt not found")
    
    if attempt.user_id != user_id:
        raise HTTPException(403, "Access denied")
    
    # Supprimer les messages associés
    msg_stmt = select(Message).where(Message.attempt_id == attempt_id)
    messages = session.exec(msg_stmt).all()
    for msg in messages:
        session.delete(msg)
    
    # Supprimer l'attempt
    session.delete(attempt)
    session.commit()
    
    return {"message": "Attempt deleted successfully", "id": str(attempt_id)}


@router.get("/users/me/stats", response_model=UserStats)
def get_user_stats(
    session: Session = Depends(get_session),
):
    """
    Récupère uniquement les statistiques de l'utilisateur.
    Endpoint léger pour dashboard.
    """
    user_id = get_current_user_id()
    
    # Statistiques des attempts
    stats_stmt = (
        select(
            func.count(Attempts.id).label("total"),
            func.count(Attempts.id).filter(Attempts.is_completed == True).label("completed"),
            func.count(Attempts.id).filter(Attempts.is_completed == False).label("in_progress"),
        )
        .where(Attempts.user_id == user_id)
    )
    
    stats_result = session.exec(stats_stmt).first()
    total_attempts = stats_result[0] if stats_result else 0
    completed_attempts = stats_result[1] if stats_result else 0
    in_progress_attempts = stats_result[2] if stats_result else 0
    
    # Nombre total de messages
    msg_stmt = (
        select(func.count(Message.id))
        .join(Attempts, Message.attempt_id == Attempts.id)
        .where(Attempts.user_id == user_id)
    )
    total_messages = session.exec(msg_stmt).first() or 0
    
    # Cases uniques
    cases_stmt = (
        select(Attempts.case_id)
        .where(Attempts.user_id == user_id)
        .distinct()
    )
    cases_attempted = [case_id for case_id in session.exec(cases_stmt).all()]
    
    return UserStats(
        total_attempts=total_attempts,
        completed_attempts=completed_attempts,
        in_progress_attempts=in_progress_attempts,
        total_messages=total_messages,
        cases_attempted=cases_attempted,
        favorite_discipline=None,
    )
