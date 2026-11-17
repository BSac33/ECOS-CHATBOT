from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from httpx import get
from sqlmodel import Session, select
from datetime import datetime, timedelta
from uuid import UUID
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Callable, ContextManager
from db import engine, get_session
import json
import os
from models import Attachment, CaseVersion, ClinicalCase, Attempts, Message, ChatRole, AttemptCreateIn, AttemptOut, ChatIn, ChatOut, ExaminerNoteOut, ModerationEvent, StationType, User, UserRole
from ai_chat_utils import generate_patient_reply
from vllm_chat_utils import get_chat_completion_vllm
from arbiter import Verdict, arbitrate, prefilter
from patient_agent import AgentEvent, CaseToolContext, DocumentRef, PatientAgentResult, StreamItem, stream_patient_agent
from attachment_routes import find_matching_attachments
from contextlib import aclosing, contextmanager, nullcontext
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
    # Un brouillon n'est jouable que par les enseignants (test : /authoring/cases/{id}/test)
    if case.status != "published" and user.role == UserRole.student:
        raise HTTPException(404, "Clinical case not found")
    
    logger.info(f"⏱️ Durée du cas: {case.duration_seconds} secondes")
    logger.info(f"case found: {case.title}")

    attempt = Attempts(user_id=user.id, case_id=payload.case_id, created_at=datetime.utcnow(), is_completed=False)

    # Version publiée en vigueur : c'est elle qui sera jouée et corrigée
    version = latest_published_version(session, case.id)
    attempt.case_version_id = version.id if version else None
    duration = version.duration_seconds if version else case.duration_seconds
    
    # Calculer l'heure de fin basée sur la durée du cas
    attempt.expires_at = attempt.created_at + timedelta(seconds=duration)
    
    session.add(attempt)
    session.commit()
    session.refresh(attempt)

    # Ajouter un message système avec les instructions pour l'étudiant
    instruction_msg = Message(
        attempt_id=attempt.id,
        role=ChatRole.system,
        content=version.student_instructions if version else case.student_instructions,
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
            "modality": m.modality,
            "interrupted_by": m.interrupted_by,
            "spoken_content": m.spoken_content,
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
    
    version = attempt_version(session, attempt)
    return {
        "case_id": case.id,
        "title": version.title if version else case.title,
        "station_type": case.station_type,
        "duration_seconds": version.duration_seconds if version else case.duration_seconds,
        "is_test": attempt.is_test,
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
#
# Un tour de chat est orchestré par `_run_turn`, partagé par deux routes :
#   POST /chat/attempts/{id}/chat         -> réponse JSON complète (CLI, anciens clients)
#   POST /chat/attempts/{id}/chat/stream  -> flux SSE (frontend, future voix)
#
# L'arbitre et le patient tournent en parallèle. Le texte du patient est mis en
# TAMPON tant que l'arbitre n'a pas rendu son verdict : rien n'est envoyé à
# l'étudiant avant validation. Une fois le message validé, le tampon est vidé
# puis le texte est relayé au fil de la génération.

EXAMINER_FINDING_PREFIX = "Examen clinique – "
EXAMINER_DOCUMENT_PREFIX = "Document affiché – "

PATIENT_ERROR_MESSAGE = "Le patient simulé n'a pas pu répondre. Réessayez dans quelques secondes."


def _use_patient_agent() -> bool:
    """Agent avec outils si le patient est servi par vLLM (désactivable)."""
    provider = os.getenv("LLM_PROVIDER", "gemini").lower()
    enabled = os.getenv("PATIENT_AGENT_ENABLED", "true").lower() in ("1", "true", "yes")
    return provider == "vllm" and enabled


def _blocked_notice(verdict: Verdict) -> str:
    if verdict.category == "ABUSIVE":
        return "Votre message a été bloqué car il a été détecté comme inapproprié, insultant ou hors charte ECOS. Merci de rester respectueux dans vos échanges."
    if verdict.category == "META_EXFILTRATION":
        return "Votre message a été bloqué : il cherche à obtenir des informations sur la grille, le scénario ou le fonctionnement de la simulation. Restez dans le cadre de la consultation."
    return "Votre message n'a pas pu être accepté par le système. Si vous pensez que c'est une erreur, contactez l'administrateur."


def _station_state(rows: list[Message]) -> list[str]:
    """Résumé de ce que l'examinateur a déjà communiqué (sans les résultats), et
    coupures de parole subies par le patient (pour qu'il puisse réagir)."""
    state = []
    for r in rows:
        if r.role == ChatRole.examiner:
            state.append(r.content.split(" : ", 1)[0])
    patient_rows = [r for r in rows if r.role == ChatRole.patient]
    cuts = sum(1 for r in patient_rows if r.interrupted_by)
    if patient_rows and patient_rows[-1].interrupted_by:
        times = "" if cuts == 1 else f" ({cuts} fois depuis le début de la consultation)"
        state.append(f"L'étudiant t'a coupé la parole pendant ta dernière réponse, tu n'avais pas fini{times}")
    return state


def _spoken(message: Message) -> str:
    """Ce que l'interlocuteur a réellement entendu (réplique coupée : partie prononcée)."""
    return message.spoken_content if message.spoken_content is not None else message.content


def latest_published_version(session: Session, case_id: int):
    stmt = (select(CaseVersion)
            .where(CaseVersion.case_id == case_id, CaseVersion.status == "published")
            .order_by(CaseVersion.version.desc()))
    return session.exec(stmt).first()


def attempt_version(session: Session, attempt: Attempts):
    return session.get(CaseVersion, attempt.case_version_id) if attempt.case_version_id else None


@contextmanager
def _write_session():
    """Session dédiée aux écritures de fin de flux SSE.

    Depuis FastAPI 0.106, la session injectée par Depends(get_session) est
    fermée AVANT l'envoi d'une StreamingResponse : le flux ouvre la sienne.
    """
    with Session(engine) as s:
        yield s


@dataclass
class _Turn:
    """Tout ce qu'il faut pour un tour, lu en base AVANT de lancer les tâches concurrentes."""
    attempt_id: UUID
    message: str
    patient_prompt: str
    history: list[dict]
    station_state: list[str]
    ctx: CaseToolContext
    use_agent: bool
    keyword_docs: list[DocumentRef] = field(default_factory=list)
    modality: str = "text"  # "voice" pour un tour dit à l'oral
    voice_id: str | None = None


def _prepare_turn(attempt_id: UUID, payload: ChatIn, session: Session, user: User, modality: str = "text") -> _Turn:
    """Validations (erreurs HTTP classiques, avant tout flux) et lecture du contexte."""
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
    
    # Version jouée (publiée, ou brouillon testé par un enseignant)
    version = attempt_version(session, attempt)
    patient_prompt = version.patient_prompt if version else case.patient_prompt
    if not patient_prompt:
        raise HTTPException(500, "Station configurée sans patient_prompt")

    stmt = select(Message).where(Message.attempt_id == attempt_id).order_by(Message.created_at)
    history_rows = session.exec(stmt).all()
    history = [
        {"role": r.role.value, "content": _spoken(r)}
        for r in history_rows
        if r.role in (ChatRole.student, ChatRole.patient)
    ]

    ctx = CaseToolContext.from_case(case)
    if version is not None:
        ctx.exam_findings = [f for f in (version.exam_findings or [])
                             if isinstance(f, dict) and f.get("id") and f.get("findings")]
    use_agent = _use_patient_agent()
    return _Turn(
        attempt_id=attempt_id,
        message=payload.message,
        patient_prompt=patient_prompt,
        history=history,
        station_state=_station_state(history_rows),
        ctx=ctx,
        use_agent=use_agent,
        keyword_docs=[] if use_agent else _keyword_documents(ctx, payload.message, case.id, session),
        modality=modality,
        voice_id=version.voice_id if version else case.voice_id,
    )


def _keyword_documents(ctx: CaseToolContext, student_message: str, case_id: int, session: Session) -> list[DocumentRef]:
    try:
        matched = find_matching_attachments(student_message, case_id, session)
    except Exception:
        logger.exception("Erreur lors de la détection des documents par mots-clés")
        return []
    matched_ids = {str(a.id) for a in matched}
    return [d for d in ctx.documents if d.attachment_id in matched_ids]


def _patient_stream(turn: _Turn) -> AsyncIterator[StreamItem]:
    if turn.use_agent:
        return stream_patient_agent(
            patient_prompt=turn.patient_prompt,
            history=turn.history,
            student_message=turn.message,
            ctx=turn.ctx,
            station_state=turn.station_state,
            oral=turn.modality == "voice",
        )
    return _legacy_stream(turn)


async def _legacy_stream(turn: _Turn) -> AsyncIterator[StreamItem]:
    """Ancien fonctionnement (Gemini ou agent désactivé) : pas d'outils, pas de flux
    token par token, documents détectés par mots-clés."""
    reply = await asyncio.to_thread(
        generate_patient_reply,
        patient_prompt=turn.patient_prompt,
        history=turn.history,
        student_message=turn.message,
    )
    result = PatientAgentResult(reply=(reply or "").strip())
    yield ("delta", result.reply)
    for doc in turn.keyword_docs:
        event = AgentEvent("document", {"document": doc})
        result.events.append(event)
        yield ("event", event)
    yield ("done", result)


def _notes_for_event(event: AgentEvent) -> list[ExaminerNoteOut]:
    if event.type == "exam_findings":
        return [
            ExaminerNoteOut(kind="exam_findings", title=f.get("label", f["id"]), content=f["findings"])
            for f in event.payload["findings"]
        ]
    if event.type == "document":
        doc: DocumentRef = event.payload["document"]
        return [ExaminerNoteOut(
            kind="document",
            title=doc.display_name,
            content=f"L'examinateur vous montre : {doc.display_name}",
            attachment_id=doc.attachment_id,
            file_url=f"/attachments/download/{doc.attachment_id}",
            mime_type=doc.mime_type,
        )]
    return []  # les signalements sont invisibles pour l'étudiant


def _persist_blocked(session: Session, turn: _Turn, verdict: Verdict) -> None:
    session.add(ModerationEvent(
        attempt_id=turn.attempt_id,
        source="arbiter",
        category=verdict.category,
        severity=verdict.tone,
        action="blocked",
        detail=verdict.detail,
        student_message=turn.message,
    ))
    session.commit()


def _persist_exchange(session: Session, turn: _Turn, result: PatientAgentResult, verdict: Verdict) -> ChatOut:
    """Étudiant -> patient -> notes de l'examinateur (dans l'ordre des outils) -> signalements."""
    t0 = datetime.now()
    tick = iter(range(1, 1000))

    def ts() -> datetime:
        return t0 + timedelta(microseconds=next(tick))

    student_msg = Message(attempt_id=turn.attempt_id, role=ChatRole.student, content=turn.message,
                          modality=turn.modality, created_at=ts())
    session.add(student_msg)
    patient_msg = Message(attempt_id=turn.attempt_id, role=ChatRole.patient, content=result.reply,
                          modality=turn.modality, created_at=ts())
    session.add(patient_msg)

    examiner_notes: list[ExaminerNoteOut] = []
    for event in result.events:
        if event.type == "exam_findings":
            for finding in event.payload["findings"]:
                label = finding.get("label", finding["id"])
                session.add(Message(
                    attempt_id=turn.attempt_id,
                    role=ChatRole.examiner,
                    content=f"{EXAMINER_FINDING_PREFIX}{label} : {finding['findings']}",
                    created_at=ts(),
                ))
        elif event.type == "document":
            doc: DocumentRef = event.payload["document"]
            session.add(Message(
                attempt_id=turn.attempt_id,
                role=ChatRole.examiner,
                content=f"{EXAMINER_DOCUMENT_PREFIX}{doc.display_name}",
                attachment_id=UUID(doc.attachment_id),
                created_at=ts(),
            ))
        examiner_notes.extend(_notes_for_event(event))

    # Signalements : arbitre (ton agressif, hors sujet accepté) + patient (outil)
    if verdict.flagged:
        session.add(ModerationEvent(
            attempt_id=turn.attempt_id,
            message_id=student_msg.id,
            source="arbiter",
            category=verdict.category,
            severity=verdict.tone,
            action="flagged",
            detail=verdict.detail,
        ))
    for flag in result.flags:
        session.add(ModerationEvent(
            attempt_id=turn.attempt_id,
            message_id=student_msg.id,
            source="patient_agent",
            category=flag["category"],
            severity=flag["severity"],
            action="flagged",
            detail=flag.get("detail"),
        ))

    session.commit()

    return ChatOut(
        patient_reply=result.reply,
        attachments=[d.attachment_id for d in result.documents] or None,
        examiner_notes=examiner_notes,
        patient_message_id=str(patient_msg.id),
    )


async def _run_turn(turn: _Turn, write_session: Callable[[], ContextManager[Session]]) -> AsyncIterator[tuple[str, Any]]:
    """Orchestre un tour. Produit, dans l'ordre :
        ("delta", str)                      texte du patient (seulement après validation)
        ("examiner_note", ExaminerNoteOut)  résultat d'outil visible par l'étudiant
        ("done", ChatOut)                   fin du tour, après persistance (bloqué ou non)
      ou ("error", (status_http, message))  échec du patient : rien n'est enregistré
    """
    # Cas flagrant (insulte explicite, demande de grille...) : verdict immédiat,
    # sans appel LLM et sans même lancer la génération du patient.
    verdict = prefilter(turn.message)
    if verdict is not None:
        with write_session() as s:
            _persist_blocked(s, turn, verdict)
        logger.info("⛔ Message bloqué par le préfiltre (%s) : %s", verdict.category, verdict.detail)
        yield ("done", ChatOut(patient_reply=_blocked_notice(verdict), blocked=True))
        return

    buffer: asyncio.Queue = asyncio.Queue()

    async def pump() -> None:
        try:
            async for item in _patient_stream(turn):
                await buffer.put(item)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("❌ Échec de la génération de la réponse patient")
            await buffer.put(("error", None))

    patient_task = asyncio.create_task(pump())
    try:
        # Ne lève jamais : en cas d'indisponibilité, le message est accepté (source="fallback")
        verdict = await arbitrate(turn.message)
        logger.info("🧭 Arbitre : %s/%s via %s en %.0f ms",
                    verdict.category, verdict.tone, verdict.source, verdict.latency_ms)

        # Message refusé : génération annulée, rien dans le transcript, incident tracé
        if not verdict.allowed:
            patient_task.cancel()
            await asyncio.wait([patient_task])
            with write_session() as s:
                _persist_blocked(s, turn, verdict)
            yield ("done", ChatOut(patient_reply=_blocked_notice(verdict), blocked=True))
            return

        # Message validé : on vide le tampon puis on relaie au fil de l'eau
        while True:
            kind, value = await buffer.get()
            if kind == "delta":
                yield ("delta", value)
            elif kind == "event":
                for note in _notes_for_event(value):
                    yield ("examiner_note", note)
            elif kind == "error":
                yield ("error", (502, PATIENT_ERROR_MESSAGE))
                return
            elif kind == "done":
                logger.info("Réponse patient générée: %s (outils: %s)", value.reply, value.tool_calls)
                with write_session() as s:
                    out = _persist_exchange(s, turn, value, verdict)
                yield ("done", out)
                return
    finally:
        # Déconnexion du client, erreur ou blocage : on n'attend pas la génération
        if not patient_task.done():
            patient_task.cancel()


@router.post("/attempts/{attempt_id}/chat", response_model=ChatOut)
async def chat(
    attempt_id: UUID, 
    payload: ChatIn, 
    session: Session = Depends(get_session), 
    user: User = Depends(check_authorization())):
    """Tour de chat, réponse JSON complète."""
    turn = _prepare_turn(attempt_id, payload, session, user)
    async with aclosing(_run_turn(turn, lambda: nullcontext(session))) as events:
        async for kind, value in events:
            if kind == "error":
                status_code, message = value
                raise HTTPException(status_code, message)
            if kind == "done":
                return value
    raise HTTPException(500, "Tour de chat interrompu")


def _sse(event: str, data: Any) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.post("/attempts/{attempt_id}/chat/stream")
async def chat_stream(
    attempt_id: UUID,
    payload: ChatIn,
    session: Session = Depends(get_session),
    user: User = Depends(check_authorization())):
    """Tour de chat en flux SSE (text/event-stream).

    Événements :
      delta          {"text": "..."}               morceau de la réplique du patient
      examiner_note  ExaminerNoteOut               résultat d'examen / document affiché
      done           ChatOut                       fin du tour (blocked=true si refusé)
      error          {"status": 502, "message": ""} échec, rien n'est enregistré

    Les erreurs de validation (404, 400, 408...) restent des réponses HTTP classiques.
    Si le client se déconnecte avant "done", la génération est annulée et rien n'est enregistré.
    """
    turn = _prepare_turn(attempt_id, payload, session, user)

    async def event_source():
        async with aclosing(_run_turn(turn, _write_session)) as events:
            async for kind, value in events:
                if kind == "delta":
                    yield _sse("delta", {"text": value})
                elif kind == "examiner_note":
                    yield _sse("examiner_note", value.model_dump())
                elif kind == "done":
                    yield _sse("done", value.model_dump())
                elif kind == "error":
                    status_code, message = value
                    yield _sse("error", {"status": status_code, "message": message})

    return StreamingResponse(
        event_source(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
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