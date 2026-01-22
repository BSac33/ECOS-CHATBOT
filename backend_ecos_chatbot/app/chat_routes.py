from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select
from datetime import datetime, timedelta
from uuid import UUID
from db import get_session
import os
from models import ClinicalCase, Attempts, Message, ChatRole, AttemptCreateIn, AttemptOut, ChatIn, ChatOut, StationType, User
from ai_chat_utils import generate_patient_reply
from vllm_chat_utils import get_chat_completion_vllm
from attachment_routes import find_matching_attachments
import logging 
import asyncio
from auth import check_authorization 

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Configurer le handler pour afficher les logs dans la console
handler = logging.StreamHandler()
handler.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

router = APIRouter()
api_key = os.getenv("GEMINI_API_KEY")

if not api_key:
    raise RuntimeError("GEMINI_API_KEY environment variable not set")

@router.post("/attempts", response_model=AttemptOut)
async def create_attempt(payload: AttemptCreateIn, session: Session = Depends(get_session), user: User = Depends(check_authorization())):
    logger.info(f"🆕 Création tentative pour le cas ID {payload.case_id}")

    case = session.get(ClinicalCase, payload.case_id)
    
    if not case:
        raise HTTPException(404, "Clinical case not found")
    
    logger.info(f"⏱️ Durée du cas: {case.duration_seconds} secondes")
    logger.info(f"case found: {case.title}")

    attempt = Attempts(user_id=user.id, case_id=payload.case_id, created_at=datetime.utcnow(), is_completed=False)
    
    # Calculer l'heure de fin basée sur la durée du cas
    attempt.expires_at = attempt.created_at + timedelta(seconds=case.duration_seconds)
    
    session.add(attempt)
    session.commit()
    session.refresh(attempt)

    # Ajouter un message système avec les instructions pour l'étudiant
    instruction_msg = Message(
        attempt_id=attempt.id,
        role=ChatRole.system,
        content=case.student_instructions,
        created_at=datetime.utcnow()
    )
    session.add(instruction_msg)
    session.commit()

    return AttemptOut(
        id=str(attempt.id),  # Sérialiser UUID en string
        case_id=attempt.case_id,
        created_at=attempt.created_at.isoformat() if attempt.created_at else datetime.utcnow().isoformat(),
        is_completed=attempt.is_completed,
    )

@router.get("/attempts/{attempt_id}/messages")
def get_messages(attempt_id: UUID, session: Session = Depends(get_session), user: User = Depends(check_authorization())):
    attempt = session.get(Attempts, attempt_id)
    if not attempt or attempt.user_id != user.id:
        raise HTTPException(404, "Attempt not found")

    stmt = select(Message).where(Message.attempt_id == attempt_id).order_by(Message.created_at)
    msgs = session.exec(stmt).all()

    return [
        {"id": str(m.id), "role": m.role, "content": m.content, "created_at": m.created_at.isoformat() if m.created_at else ""}
        for m in msgs
    ]


@router.get("/attempts/{attempt_id}/time-remaining")
def get_time_remaining(
    attempt_id: UUID, 
    session: Session = Depends(get_session),
    user: User = Depends(check_authorization())
):
    """Récupère le temps restant pour une tentative"""
    attempt = session.get(Attempts, attempt_id)
    if not attempt or attempt.user_id != user.id:
        raise HTTPException(404, "Attempt not found")

    if attempt.is_completed:
        return {
            "is_expired": True,
            "seconds_remaining": 0,
            "message": "Session terminée"
        }

    if not attempt.expires_at:
        return {
            "is_expired": False,
            "seconds_remaining": None,
            "message": "Le chronomètre n'a pas encore été démarré"
        }

    now = datetime.utcnow()
    if now > attempt.expires_at:
        return {
            "is_expired": True,
            "seconds_remaining": 0,
            "message": "Temps écoulé"
        }

    remaining = (attempt.expires_at - now).total_seconds()
    return {
        "is_expired": False,
        "seconds_remaining": int(remaining),
        "expires_at": attempt.expires_at.isoformat()
    }


@router.post("/attempts/{attempt_id}/chat", response_model=ChatOut)
async def chat(attempt_id: UUID, payload: ChatIn, session: Session = Depends(get_session), user: User = Depends(check_authorization())):
    attempt = session.get(Attempts, attempt_id)
    if not attempt or attempt.user_id != user.id:
        raise HTTPException(404, "Attempt not found")
    if attempt.is_completed:
        raise HTTPException(400, "Attempt already completed")

    case = session.get(ClinicalCase, attempt.case_id)
    if not case:
        raise HTTPException(500, "Case missing (DB integrity error)")

    # Vérifier si le temps est écoulé
    now = datetime.utcnow()
    if attempt.expires_at and now > attempt.expires_at:
        # Finaliser automatiquement la tentative
        attempt.is_completed = True
        attempt.completed_at = attempt.expires_at  # Utiliser l'heure d'expiration
        session.add(attempt)
        session.commit()
        
        raise HTTPException(
            408,  # Request Timeout
            f"Le temps imparti ({case.duration_seconds // 60} minutes) est écoulé. "
            "La session a été automatiquement finalisée. "
            "Vous pouvez maintenant procéder à l'évaluation."
        )

    # 1) charger l'historique
    stmt = select(Message).where(Message.attempt_id == attempt_id).order_by(Message.created_at)
    history_rows = session.exec(stmt).all()

    history = [{"role": r.role.value, "content": r.content} for r in history_rows if r.role != ChatRole.system]

    # 2) Détecter si le message de l'étudiant déclenche des attachments
    matched_attachments = find_matching_attachments(
        message=payload.message,
        case_id=case.id or 0,  # Fallback si None (ne devrait pas arriver)
        db=session
    )
    
    # Préparer le contexte pour le LLM avec les fichiers disponibles
    attachment_context = ""
    if matched_attachments:
        attachment_context = "\n\n[EXAMENS DISPONIBLES]\n"
        for att in matched_attachments:
            attachment_context += f"- {att.display_name}"
            if att.description:
                attachment_context += f": {att.description}"
            attachment_context += "\n"

    # Vérifier que la station nécessite une impersonation patient
    # Pour les stations d'analyse (exam_analysis, procedure), il n'y a PAS de conversation en temps réel
    requires_patient_impersonation = case.station_type in [
        StationType.patient_interview,
        StationType.diagnosis_announcement,
        StationType.mixed
    ]
    
    if not requires_patient_impersonation:
        raise HTTPException(
            400, 
            "Cette station ne supporte pas le chat en temps réel. "
            "L'étudiant doit soumettre sa réponse complète puis demander l'évaluation via /attempts/{id}/evaluate"
        )
    
    if not case.patient_prompt:
        raise HTTPException(500, "Station configurée sans patient_prompt")

    # Générer la réponse du patient
    reply = generate_patient_reply(
        patient_prompt=case.patient_prompt + attachment_context,
        history=history,
        student_message=payload.message,
    )
    
    logger.info(f"Réponse patient générée: {reply}")

    # Écrire en DB en une transaction
    student_msg = Message(
        attempt_id=attempt_id,
        role=ChatRole.student,
        content=payload.message,
    )
    
    # Si des attachments ont été déclenchés, lier le premier au message
    attachment_id = matched_attachments[0].id if matched_attachments else None
    
    reply_msg = Message(
        attempt_id=attempt_id,
        role=ChatRole.patient,
        content=reply,
        attachment_id=attachment_id
    )

    session.add(student_msg)
    session.add(reply_msg)
    session.commit()

    # 5) Retourner la réponse avec les UUIDs des attachments
    attachment_ids = [str(att.id) for att in matched_attachments] if matched_attachments else None

    return ChatOut(
        patient_reply=reply,
        attachments=attachment_ids
    )

@router.post("/attempts/{attempt_id}/finalize")
def finalize_attempt(attempt_id: UUID, session: Session = Depends(get_session), user: User = Depends(check_authorization())):
    attempt = session.get(Attempts, attempt_id)
    if not attempt or attempt.user_id != user.id:
        raise HTTPException(404, "Attempt not found")

    attempt.is_completed = True
    attempt.completed_at = datetime.utcnow()  # Enregistrer le timestamp de finalisation
    session.add(attempt)
    session.commit()

    return {"status": "ok", "completed_at": attempt.completed_at.isoformat()}

@router.post("test-chat")
def test_chat():
    response = get_chat_completion_vllm()
    if response:
        return response
    else:   
        raise HTTPException(500, "Erreur lors de l'appel à vLLM")