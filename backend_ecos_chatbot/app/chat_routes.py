from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from httpx import get
from sqlmodel import Session, select
from datetime import datetime, timedelta
from uuid import UUID
from db import get_session
import os
import json
from models import ClinicalCase, Attempts, Message, ChatRole, AttemptCreateIn, AttemptOut, ChatIn, ChatOut, WrittenAnswerIn, StationType, User, Attachment, AttachmentOut
from ai_chat_utils import generate_patient_reply
from vllm_chat_utils import get_chat_completion_vllm, classify_student_message_vllm_arbiter, generate_patient_reply_vllm_stream, ArbiterOutput
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
    
    # 1 + 3. Arbitre ET réponse patient en PARALLÈLE (asyncio.to_thread)
    # L'arbitre (modèle léger, ~1s) et la génération patient (modèle principal, ~3-5s)
    # tournent simultanément. Si l'arbitre bloque le message, la réponse patient est
    # simplement ignorée. Politique fail-open : tout erreur de l'arbitre → on laisse passer.
    _ARBITER_FALLBACK = {
        "category": "OTHER", "tone": "NEUTRAL",
        "exam": {"requested": False, "label": None, "confidence": None},
        "safety": {"allow_to_transcript": True, "redact": False, "redacted_text": None}
    }
    _REPLY_FALLBACK = "Je n'ai pas bien entendu, pouvez-vous répéter ?"

    logger.info("⚡ Lancement parallèle : arbitre + génération patient")
    results = await asyncio.gather(
        asyncio.to_thread(classify_student_message_vllm_arbiter, case.attachments, payload.message),
        asyncio.to_thread(generate_patient_reply, case.patient_prompt, history, payload.message),
        return_exceptions=True
    )

    arbiter = results[0] if not isinstance(results[0], Exception) else _ARBITER_FALLBACK
    reply   = results[1] if not isinstance(results[1], Exception) else _REPLY_FALLBACK

    if isinstance(results[0], Exception):
        logger.warning(f"⚠️ Arbitre en erreur, fail-open: {results[0]}")
    if isinstance(results[1], Exception):
        logger.error(f"❌ Génération patient en erreur: {results[1]}")

    # 2. Évaluer la décision de blocage — politique fail-open
    cat = arbiter.get("category", "OTHER")
    arbiter_blocks = not arbiter["safety"]["allow_to_transcript"]
    is_hard_block      = arbiter_blocks and cat == "ABUSIVE"
    is_meta_exfiltration = arbiter_blocks and cat == "META"

    if is_hard_block:
        return ChatOut(
            patient_reply="Votre message a été bloqué car il a été détecté comme insultant ou menaçant. Merci de rester respectueux.",
            attachments=None
        )

    if is_meta_exfiltration:
        logger.warning(f"⚠️ Tentative META/exfiltration: {payload.message[:80]}")
        return ChatOut(
            patient_reply="Le patient ne peut pas répondre à cette question. Restez dans le cadre de la simulation clinique.",
            attachments=None
        )

    if cat == "EXAM_REQUEST":
        logger.info("Demande d'examen complémentaire : %s", arbiter["exam"])

    logger.info(f"✅ Réponse patient ({len(reply)} car.) | catégorie={cat}")

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

@router.post("/attempts/{attempt_id}/chat/stream")
async def chat_stream(
    attempt_id: UUID,
    payload: ChatIn,
    session: Session = Depends(get_session),
    user: User = Depends(check_authorization())
):
    """
    Endpoint SSE : stream la réponse patient token par token.
    Format SSE :
      data: {"type":"token","content":"..."}\n\n
      data: {"type":"done","patient_reply":"...","attachments":null}\n\n
      data: {"type":"error","detail":"..."}\n\n
    """
    attempt = session.get(Attempts, attempt_id)
    if not attempt or attempt.user_id != user.id:
        raise HTTPException(404, "Attempt not found")
    if attempt.is_completed:
        raise HTTPException(400, "Attempt already completed")

    case = session.get(ClinicalCase, attempt.case_id)
    if not case:
        raise HTTPException(500, "Case missing (DB integrity error)")

    now = datetime.utcnow()
    if attempt.expires_at and now > attempt.expires_at:
        attempt.is_completed = True
        attempt.completed_at = attempt.expires_at
        session.add(attempt)
        session.commit()
        raise HTTPException(408, f"Le temps imparti est écoulé.")

    requires_patient_impersonation = case.station_type in [
        StationType.patient_interview,
        StationType.diagnosis_announcement,
        StationType.mixed
    ]
    if not requires_patient_impersonation:
        raise HTTPException(400, "Cette station ne supporte pas le chat en temps réel.")
    if not case.patient_prompt:
        raise HTTPException(500, "Station configurée sans patient_prompt")

    stmt = select(Message).where(Message.attempt_id == attempt_id).order_by(Message.created_at)
    history_rows = session.exec(stmt).all()
    history = [{"role": r.role.value, "content": r.content} for r in history_rows if r.role != ChatRole.system]

    # Détacher les données nécessaires pour éviter les erreurs de session en dehors de la requête
    patient_prompt = case.patient_prompt
    case_attachments = list(case.attachments)
    message_text = payload.message

    _ARBITER_FALLBACK = {
        "category": "OTHER", "tone": "NEUTRAL",
        "exam": {"requested": False, "label": None, "confidence": None},
        "safety": {"allow_to_transcript": True, "redact": False, "redacted_text": None}
    }

    async def event_stream():
        # 1. Arbitre en parallèle avec première partie du streaming
        arbiter_task = asyncio.create_task(
            asyncio.to_thread(classify_student_message_vllm_arbiter, case_attachments, message_text)
        )

        # 2. Attendre l'arbitre (rapide ~1-2s) avant de streamer
        try:
            arbiter = await arbiter_task
        except Exception as e:
            logger.warning(f"⚠️ Arbitre en erreur, fail-open: {e}")
            arbiter = _ARBITER_FALLBACK

        cat = arbiter.get("category", "OTHER")
        arbiter_blocks = not arbiter["safety"]["allow_to_transcript"]
        is_hard_block = arbiter_blocks and cat == "ABUSIVE"
        is_meta_exfiltration = arbiter_blocks and cat == "META"

        if is_hard_block:
            msg = "Votre message a été bloqué car il a été détecté comme insultant ou menaçant. Merci de rester respectueux."
            yield f"data: {json.dumps({'type': 'done', 'patient_reply': msg, 'attachments': None})}\n\n"
            return

        if is_meta_exfiltration:
            logger.warning(f"⚠️ Tentative META/exfiltration: {message_text[:80]}")
            msg = "Le patient ne peut pas répondre à cette question. Restez dans le cadre de la simulation clinique."
            yield f"data: {json.dumps({'type': 'done', 'patient_reply': msg, 'attachments': None})}\n\n"
            return

        # 3. Streamer la réponse patient token par token via queue async
        loop = asyncio.get_running_loop()
        q: asyncio.Queue = asyncio.Queue()

        def run_stream():
            try:
                for chunk in generate_patient_reply_vllm_stream(patient_prompt, history, message_text):
                    loop.call_soon_threadsafe(q.put_nowait, chunk)
            except Exception as exc:
                loop.call_soon_threadsafe(q.put_nowait, exc)
            finally:
                loop.call_soon_threadsafe(q.put_nowait, None)  # sentinel

        stream_future = loop.run_in_executor(None, run_stream)

        full_reply = ""
        while True:
            item = await q.get()
            if item is None:
                break
            if isinstance(item, Exception):
                logger.error(f"❌ Erreur streaming patient: {item}")
                if not full_reply:
                    full_reply = "Je n'ai pas bien entendu, pouvez-vous répéter ?"
                    yield f"data: {json.dumps({'type': 'token', 'content': full_reply})}\n\n"
                break
            full_reply += item
            yield f"data: {json.dumps({'type': 'token', 'content': item})}\n\n"

        await stream_future

        # 4. Persister en base
        try:
            matched_attachments = find_matching_attachments(case_attachments, message_text)
        except Exception:
            matched_attachments = []
        attachment_id = matched_attachments[0].id if matched_attachments else None
        attachment_ids = [str(att.id) for att in matched_attachments] if matched_attachments else None

        student_msg = Message(attempt_id=attempt_id, role=ChatRole.student, content=message_text)
        reply_msg = Message(attempt_id=attempt_id, role=ChatRole.patient, content=full_reply, attachment_id=attachment_id)
        session.add(student_msg)
        session.add(reply_msg)
        session.commit()

        yield f"data: {json.dumps({'type': 'done', 'patient_reply': full_reply, 'attachments': attachment_ids})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


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