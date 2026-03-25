from fastapi import APIRouter, Depends, HTTPException
from httpx import get
from sqlmodel import Session, select
from datetime import datetime, timedelta
from uuid import UUID
from db import get_session
import os
from models import ClinicalCase, Attempts, Message, ChatRole, AttemptCreateIn, AttemptOut, ChatIn, ChatOut, WrittenAnswerIn, StationType, User, Attachment, AttachmentOut
from ai_chat_utils import generate_patient_reply
from vllm_chat_utils import get_chat_completion_vllm, classify_student_message_vllm_arbiter, ArbiterOutput
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

@router.get("/cases/{case_id}/active-attempt", response_model=AttemptOut | None)
async def get_active_attempt(case_id: int, session: Session = Depends(get_session), user: User = Depends(check_authorization())):
    """
    Récupère l'attempt actif (non complété et non expiré) pour un cas et un utilisateur donné.
    Retourne None s'il n'y en a pas.
    """
    logger.info(f"🔍 Recherche attempt actif pour cas {case_id} et user {user.id}")
    
    # Chercher un attempt non complété pour ce cas et cet utilisateur
    stmt = select(Attempts).where(
        Attempts.case_id == case_id,
        Attempts.user_id == user.id,
        Attempts.is_completed == False
    ).order_by(Attempts.created_at.desc())
    
    attempt = session.exec(stmt).first()
    
    if not attempt:
        logger.info(f"❌ Aucun attempt actif trouvé")
        return None
    
    # Vérifier si l'attempt n'est pas expiré
    now = datetime.utcnow()
    if attempt.expires_at and now > attempt.expires_at:
        logger.info(f"⏰ Attempt {attempt.id} expiré, finalisation automatique...")
        # Auto-finaliser l'attempt expiré
        attempt.is_completed = True
        attempt.completed_at = attempt.expires_at
        session.add(attempt)
        session.commit()
        return None
    
    logger.info(f"✅ Attempt actif trouvé : {attempt.id}")
    return AttemptOut(
        id=str(attempt.id),
        case_id=attempt.case_id,
        created_at=attempt.created_at.isoformat() if attempt.created_at else datetime.utcnow().isoformat(),
        is_completed=attempt.is_completed,
    )

@router.post("/attempts", response_model=AttemptOut)
async def create_attempt(
    payload: AttemptCreateIn, 
    session: Session = Depends(get_session), 
    user: User = Depends(check_authorization())):
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

@router.get("/attempts/{attempt_id}/case-info")
def get_case_info(attempt_id: UUID, session: Session = Depends(get_session), user: User = Depends(check_authorization())):
    """Récupère les informations du cas clinique associé à un attempt"""
    attempt = session.get(Attempts, attempt_id)
    if not attempt or attempt.user_id != user.id:
        raise HTTPException(404, "Attempt not found")
    
    case = session.get(ClinicalCase, attempt.case_id)
    if not case:
        raise HTTPException(500, "Case not found")
    
    return {
        "case_id": case.id,
        "title": case.title,
        "station_type": case.station_type,
        "duration_seconds": case.duration_seconds
    }


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
async def chat(
    attempt_id: UUID, 
    payload: ChatIn, 
    session: Session = Depends(get_session), 
    user: User = Depends(check_authorization())):
    
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
    
    # 1. Appel à l'arbitre (LLM)
    arbiter = classify_student_message_vllm_arbiter(case.attachments, payload.message)
    if not arbiter:
        raise HTTPException(500, "Erreur lors de l'arbitrage du message étudiant")

    # 2. Si le message est refusé (allow_to_transcript == False), ne rien stocker et retourner un message system explicite
    if not arbiter["safety"]["allow_to_transcript"]:
        # Personnalisation du message selon la catégorie
        cat = arbiter.get("category", "OTHER")
        if cat == "ABUSIVE":
            reason = "Votre message a été bloqué car il a été détecté comme inapproprié, insultant ou hors charte ECOS. Merci de rester respectueux dans vos échanges."
        elif cat == "OFF_TOPIC":
            reason = "Votre message a été jugé hors sujet pour cette station ECOS. Merci de rester dans le cadre de la simulation."
        else:
            reason = "Votre message n'a pas pu être accepté par le système. Si vous pensez que c'est une erreur, contactez l'administrateur."
        # Si un texte masqué est proposé, l'afficher
        redacted = arbiter["safety"].get("redacted_text")
        if redacted:
            reason += f"\nVersion modérée proposée : {redacted}"
        return ChatOut(
            patient_reply=reason,
            attachments=None
        )

    # 3. Génération de la réponse patient selon la catégorie
    cat = arbiter.get("category", "OTHER")
    # Optionnel : comportement spécial selon la catégorie
    if cat == "EXAM_REQUEST":
        # On peut logguer ou traiter différemment si besoin
        logger.info("L'étudiant a demandé un examen complémentaire : %s", arbiter["exam"])
    elif cat == "EMPATHY":
        logger.info("Message d'empathie détecté")
    elif cat == "OFF_TOPIC":
        logger.info("Message hors sujet mais accepté")

    # Générer la réponse du patient
    reply = generate_patient_reply(
        patient_prompt=case.patient_prompt,
        history=history,
        student_message=payload.message,
    )
    logger.info(f"Réponse patient générée: {reply}")

    # 4. Stockage en base UNIQUEMENT si le message est accepté
    student_msg = Message(
        attempt_id=attempt_id,
        role=ChatRole.student,
        content=payload.message,
    )
    # Si des attachments ont été déclenchés, lier le premier au message
    # matched_attachments doit être défini (sinon, à corriger plus tard)
    try:
        matched_attachments = find_matching_attachments(case.attachments, payload.message)
    except Exception:
        matched_attachments = []
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
    # Retourner la réponse avec les UUIDs des attachments
    attachment_ids = [str(att.id) for att in matched_attachments] if matched_attachments else None
    return ChatOut(
        patient_reply=reply,
        attachments=attachment_ids
    )

@router.post("/attempts/{attempt_id}/submit-answer")
def submit_written_answer(
    attempt_id: UUID,
    payload: WrittenAnswerIn,
    session: Session = Depends(get_session),
    user: User = Depends(check_authorization())
):
    """
    Soumet la réponse écrite d'un étudiant pour les stations sans chat patient
    (exam_analysis, procedure). Stocke la réponse comme message étudiant.

    Peut être appelé plusieurs fois : la réponse précédente est remplacée.
    """
    attempt = session.get(Attempts, attempt_id)
    if not attempt or attempt.user_id != user.id:
        raise HTTPException(404, "Attempt not found")
    if attempt.is_completed:
        raise HTTPException(400, "Attempt already completed")

    case = session.get(ClinicalCase, attempt.case_id)
    if not case:
        raise HTTPException(500, "Case missing")

    # Vérifier que ce type de station accepte les réponses écrites
    written_station_types = [StationType.exam_analysis, StationType.procedure]
    if case.station_type not in written_station_types:
        raise HTTPException(
            400,
            "Cette station nécessite un chat patient, pas une réponse écrite. "
            "Utilisez POST /attempts/{id}/chat."
        )

    if not payload.answer.strip():
        raise HTTPException(400, "La réponse ne peut pas être vide.")

    # Vérifier le temps
    now = datetime.utcnow()
    if attempt.expires_at and now > attempt.expires_at:
        attempt.is_completed = True
        attempt.completed_at = attempt.expires_at
        session.add(attempt)
        session.commit()
        raise HTTPException(408, "Le temps imparti est écoulé. La session a été finalisée.")

    # Supprimer toute réponse écrite précédente (pour permettre la mise à jour)
    existing_stmt = select(Message).where(
        Message.attempt_id == attempt_id,
        Message.role == ChatRole.student
    )
    existing_answers = session.exec(existing_stmt).all()
    for msg in existing_answers:
        session.delete(msg)
    session.commit()

    # Enregistrer la nouvelle réponse
    answer_msg = Message(
        attempt_id=attempt_id,
        role=ChatRole.student,
        content=payload.answer,
        created_at=datetime.utcnow()
    )
    session.add(answer_msg)
    session.commit()

    return {"status": "ok", "message": "Réponse enregistrée avec succès."}


@router.get("/attempts/{attempt_id}/exam-attachments", response_model=list[AttachmentOut])
def get_exam_attachments(
    attempt_id: UUID,
    session: Session = Depends(get_session),
    user: User = Depends(check_authorization())
):
    """
    Récupère les pièces jointes iconographiques (show_at_start=True) pour une tentative.
    Utilisé par les stations écrites (exam_analysis, procedure) pour afficher
    l'iconographie au début de l'examen.
    """
    attempt = session.get(Attempts, attempt_id)
    if not attempt or attempt.user_id != user.id:
        raise HTTPException(404, "Attempt not found")

    stmt = select(Attachment).where(
        Attachment.case_id == attempt.case_id,
        Attachment.show_at_start == True
    )
    attachments = session.exec(stmt).all()

    return [
        AttachmentOut(
            id=str(a.id),
            filename=a.filename,
            display_name=a.display_name,
            kind=a.kind,
            mime_type=a.mime_type,
            size_bytes=a.size_bytes or 0,
            file_url=a.file_url,
            uploaded_at=a.uploaded_at.isoformat(),
            show_at_start=a.show_at_start,
        )
        for a in attachments
    ]


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