from fastapi import APIRouter, Depends, HTTPException
from httpx import get
from sqlmodel import Session, select
from datetime import datetime, timedelta
from uuid import UUID
from db import get_session
import os
from models import Attachment, ClinicalCase, Attempts, Message, ChatRole, AttemptCreateIn, AttemptOut, ChatIn, ChatOut, ExaminerNoteOut, ModerationEvent, StationType, User
from ai_chat_utils import generate_patient_reply
from vllm_chat_utils import get_chat_completion_vllm, classify_student_message_vllm_arbiter, ArbiterOutput
from patient_agent import AgentEvent, CaseToolContext, PatientAgentResult, run_patient_agent
from attachment_routes import find_matching_attachments
from contextlib import suppress
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

    attachment_ids = {m.attachment_id for m in msgs if m.attachment_id}
    mime_types = {}
    if attachment_ids:
        attachments = session.exec(select(Attachment).where(Attachment.id.in_(attachment_ids))).all()
        mime_types = {a.id: a.mime_type for a in attachments}

    return [
        {
            "id": str(m.id),
            "role": m.role,
            "content": m.content,
            "attachment_id": str(m.attachment_id) if m.attachment_id else None,
            "attachment_mime_type": mime_types.get(m.attachment_id),
            "created_at": m.created_at.isoformat() if m.created_at else "",
        }
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


# ==================== CHAT : AGENT PATIENT + GARDE-FOUS ====================

EXAMINER_FINDING_PREFIX = "Examen clinique – "
EXAMINER_DOCUMENT_PREFIX = "Document affiché – "

# Tons/catégories de l'arbitre qui, sans bloquer le message, sont tracés
FLAGGED_TONES = {"AGGRESSIVE", "INSULTING"}
FLAGGED_CATEGORIES = {"OFF_TOPIC"}


def _use_patient_agent() -> bool:
    """Agent avec outils si le patient est servi par vLLM (désactivable)."""
    provider = os.getenv("LLM_PROVIDER", "gemini").lower()
    enabled = os.getenv("PATIENT_AGENT_ENABLED", "true").lower() in ("1", "true", "yes")
    return provider == "vllm" and enabled


def _blocked_notice(arbiter: dict) -> str:
    cat = arbiter.get("category", "OTHER")
    if cat == "ABUSIVE":
        reason = "Votre message a été bloqué car il a été détecté comme inapproprié, insultant ou hors charte ECOS. Merci de rester respectueux dans vos échanges."
    elif cat == "OFF_TOPIC":
        reason = "Votre message a été jugé hors sujet pour cette station ECOS. Merci de rester dans le cadre de la simulation."
    else:
        reason = "Votre message n'a pas pu être accepté par le système. Si vous pensez que c'est une erreur, contactez l'administrateur."
    redacted = (arbiter.get("safety") or {}).get("redacted_text")
    if redacted:
        reason += f"\nVersion modérée proposée : {redacted}"
    return reason


def _station_state(rows: list[Message]) -> list[str]:
    """Résumé de ce que l'examinateur a déjà communiqué (sans les résultats)."""
    state = []
    for r in rows:
        if r.role == ChatRole.examiner:
            state.append(r.content.split(" : ", 1)[0])
    return state


async def _generate_legacy(patient_prompt: str, history: list[dict], student_message: str, keyword_docs: list) -> PatientAgentResult:
    """Ancien fonctionnement (Gemini ou agent désactivé) : pas d'outils, documents par mots-clés."""
    reply = await asyncio.to_thread(
        generate_patient_reply,
        patient_prompt=patient_prompt,
        history=history,
        student_message=student_message,
    )
    return PatientAgentResult(
        reply=reply,
        events=[AgentEvent("document", {"document": doc}) for doc in keyword_docs],
    )


def _keyword_documents(ctx: CaseToolContext, student_message: str, case_id: int, session: Session) -> list:
    try:
        matched = find_matching_attachments(student_message, case_id, session)
    except Exception:
        logger.exception("Erreur lors de la détection des documents par mots-clés")
        return []
    matched_ids = {str(a.id) for a in matched}
    return [d for d in ctx.documents if d.attachment_id in matched_ids]


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

    # 1) Charger l'historique
    stmt = select(Message).where(Message.attempt_id == attempt_id).order_by(Message.created_at)
    history_rows = session.exec(stmt).all()
    history = [
        {"role": r.role.value, "content": r.content}
        for r in history_rows
        if r.role in (ChatRole.student, ChatRole.patient)
    ]

    # Tout ce qui touche la base est lu AVANT de lancer les tâches concurrentes
    ctx = CaseToolContext.from_case(case)
    attachment_names = [d.display_name for d in ctx.documents]

    # 2) Arbitre et patient EN PARALLÈLE : la latence est max(arbitre, patient)
    #    au lieu de leur somme. La réponse du patient n'est libérée qu'après le
    #    verdict de l'arbitre ; les outils n'ont aucun effet de bord avant ce point.
    if _use_patient_agent():
        patient_task = asyncio.create_task(run_patient_agent(
            patient_prompt=case.patient_prompt,
            history=history,
            student_message=payload.message,
            ctx=ctx,
            station_state=_station_state(history_rows),
        ))
    else:
        keyword_docs = _keyword_documents(ctx, payload.message, case.id, session)
        patient_task = asyncio.create_task(
            _generate_legacy(case.patient_prompt, history, payload.message, keyword_docs)
        )

    try:
        arbiter = await asyncio.to_thread(
            classify_student_message_vllm_arbiter, attachment_names, payload.message
        )
    except Exception:
        patient_task.cancel()
        raise
    if not arbiter:
        patient_task.cancel()
        raise HTTPException(500, "Erreur lors de l'arbitrage du message étudiant")

    category = arbiter.get("category", "OTHER")
    tone = arbiter.get("tone", "NEUTRAL")

    # 3) Message refusé : on annule la génération, rien n'entre dans le transcript,
    #    mais l'incident est tracé pour l'enseignant.
    if not (arbiter.get("safety") or {}).get("allow_to_transcript", True):
        patient_task.cancel()
        with suppress(asyncio.CancelledError, Exception):
            await patient_task
        session.add(ModerationEvent(
            attempt_id=attempt_id,
            source="arbiter",
            category=category,
            severity=tone,
            action="blocked",
            detail=(arbiter.get("safety") or {}).get("redacted_text"),
            student_message=payload.message,
        ))
        session.commit()
        logger.info("⛔ Message bloqué par l'arbitre (%s/%s)", category, tone)
        return ChatOut(patient_reply=_blocked_notice(arbiter), blocked=True)

    if category == "EXAM_REQUEST":
        logger.info("L'étudiant a demandé un examen complémentaire : %s", arbiter.get("exam"))

    # 4) Réponse du patient (avec outils éventuels)
    try:
        result = await patient_task
    except Exception:
        logger.exception("❌ Échec de la génération de la réponse patient")
        raise HTTPException(502, "Le patient simulé n'a pas pu répondre. Réessayez dans quelques secondes.")
    logger.info("Réponse patient générée: %s (outils: %s)", result.reply, result.tool_calls)

    # 5) Persistance : étudiant -> patient -> notes de l'examinateur
    t0 = datetime.now()
    tick = iter(range(1, 1000))

    def ts() -> datetime:
        return t0 + timedelta(microseconds=next(tick))

    student_msg = Message(attempt_id=attempt_id, role=ChatRole.student, content=payload.message, created_at=ts())
    reply_msg = Message(attempt_id=attempt_id, role=ChatRole.patient, content=result.reply, created_at=ts())
    session.add(student_msg)
    session.add(reply_msg)

    examiner_notes: list[ExaminerNoteOut] = []
    for finding in result.findings:
        label = finding.get("label", finding["id"])
        session.add(Message(
            attempt_id=attempt_id,
            role=ChatRole.examiner,
            content=f"{EXAMINER_FINDING_PREFIX}{label} : {finding['findings']}",
            created_at=ts(),
        ))
        examiner_notes.append(ExaminerNoteOut(kind="exam_findings", title=label, content=finding["findings"]))

    for doc in result.documents:
        session.add(Message(
            attempt_id=attempt_id,
            role=ChatRole.examiner,
            content=f"{EXAMINER_DOCUMENT_PREFIX}{doc.display_name}",
            attachment_id=UUID(doc.attachment_id),
            created_at=ts(),
        ))
        examiner_notes.append(ExaminerNoteOut(
            kind="document",
            title=doc.display_name,
            content=f"L'examinateur vous montre : {doc.display_name}",
            attachment_id=doc.attachment_id,
            file_url=f"/attachments/download/{doc.attachment_id}",
            mime_type=doc.mime_type,
        ))

    # Signalements : arbitre (ton agressif, hors sujet accepté) + patient (outil)
    if tone in FLAGGED_TONES or category in FLAGGED_CATEGORIES:
        session.add(ModerationEvent(
            attempt_id=attempt_id,
            message_id=student_msg.id,
            source="arbiter",
            category=category,
            severity=tone,
            action="flagged",
        ))
    for flag in result.flags:
        session.add(ModerationEvent(
            attempt_id=attempt_id,
            message_id=student_msg.id,
            source="patient_agent",
            category=flag["category"],
            severity=flag["severity"],
            action="flagged",
            detail=flag.get("detail"),
        ))

    session.commit()

    attachment_ids = [d.attachment_id for d in result.documents] or None
    return ChatOut(
        patient_reply=result.reply,
        attachments=attachment_ids,
        examiner_notes=examiner_notes,
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