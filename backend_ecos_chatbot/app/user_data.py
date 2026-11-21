# user_data.py
"""
Données personnelles d'un utilisateur (RGPD) : export, suppression d'une tentative ou du
compte, purge des tentatives anciennes. Les suppressions suivent l'ordre des clés
étrangères (fonctionne sur PostgreSQL, sans dépendre de cascades en base).
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List
from uuid import UUID

from sqlmodel import Session, select

from models import (
    Attachment, Attempts, CaseVersion, ClinicalCase, EvaluationItemResult, EvaluationResult, Message,
    ModerationEvent, User,
)


class UserDeletionRefused(Exception):
    """Compte non supprimable (auteur de stations) : à traiter par un administrateur."""


def delete_attempt(session: Session, attempt_id: UUID) -> None:
    """Supprime une tentative et tout ce qui en dépend (sans commit)."""
    for model in (EvaluationItemResult, EvaluationResult, ModerationEvent):
        for row in session.exec(select(model).where(model.attempt_id == attempt_id)).all():
            session.delete(row)
    session.flush()
    for att in session.exec(select(Attachment).where(Attachment.attempt_id == attempt_id)).all():
        att.attempt_id = None
        session.add(att)
    for msg in session.exec(select(Message).where(Message.attempt_id == attempt_id)).all():
        session.delete(msg)
    session.flush()
    attempt = session.get(Attempts, attempt_id)
    if attempt is not None:
        session.delete(attempt)


def export_user(session: Session, user: User) -> Dict[str, Any]:
    """Toutes les données de l'utilisateur, lisibles (article 15 et 20 du RGPD)."""
    attempts: List[Dict[str, Any]] = []
    for att in session.exec(select(Attempts).where(Attempts.user_id == user.id)
                            .order_by(Attempts.created_at)).all():
        case = session.get(ClinicalCase, att.case_id)
        messages = session.exec(select(Message).where(Message.attempt_id == att.id)
                                .order_by(Message.created_at)).all()
        evaluation = session.exec(select(EvaluationResult).where(EvaluationResult.attempt_id == att.id)).first()
        events = session.exec(select(ModerationEvent).where(ModerationEvent.attempt_id == att.id)).all()
        attempts.append({
            "id": str(att.id), "station": case.title if case else None,
            "debut": att.created_at.isoformat() if att.created_at else None,
            "fin": att.completed_at.isoformat() if att.completed_at else None,
            "test_enseignant": bool(getattr(att, "is_test", False)),
            "messages": [{"role": m.role.value, "contenu": m.content, "modalite": m.modality,
                          "coupe_par": m.interrupted_by, "date": m.created_at.isoformat() if m.created_at else None}
                         for m in messages],
            "correction": evaluation.evaluation_data.get("evaluation") if evaluation else None,
            "signalements": [{"categorie": e.category, "gravite": e.severity, "action": e.action,
                              "detail": e.detail} for e in events],
        })
    return {
        "export": {"date": datetime.now().isoformat(timespec="seconds"), "application": "ECOS Chatbot"},
        "compte": {"identifiant": user.username, "nom": user.full_name, "email": getattr(user, "email", None),
                   "role": user.role.value, "actif": user.is_active},
        "tentatives": attempts,
    }


def delete_user(session: Session, user: User) -> None:
    """Supprime le compte et toutes ses tentatives (sans commit). Refusé pour l'auteur de
    stations : ses contenus doivent d'abord être transférés par un administrateur."""
    authored = session.exec(select(ClinicalCase).where(ClinicalCase.created_by == user.id)).first() \
        or session.exec(select(CaseVersion).where(CaseVersion.created_by == user.id)).first()
    if authored is not None:
        raise UserDeletionRefused("Ce compte est l'auteur de stations : un administrateur doit d'abord les "
                                  "transférer à un autre enseignant.")
    for att in session.exec(select(Attempts).where(Attempts.user_id == user.id)).all():
        delete_attempt(session, att.id)
    for case in session.exec(select(ClinicalCase).where(ClinicalCase.reviewed_by == user.id)).all():
        case.reviewed_by = None
        session.add(case)
    session.flush()
    session.delete(session.get(User, user.id))


def purge_attempts(session: Session, before: datetime, include_tests: bool = True) -> int:
    """Supprime les tentatives commencées avant `before` ; renvoie leur nombre (avec commit)."""
    stmt = select(Attempts.id).where(Attempts.created_at < before)
    if not include_tests:
        stmt = stmt.where(Attempts.is_test == False)  # noqa: E712
    ids = list(session.exec(stmt).all())
    for attempt_id in ids:
        delete_attempt(session, attempt_id)
        session.commit()
    return len(ids)
