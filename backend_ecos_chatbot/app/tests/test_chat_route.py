"""Tests de la route /chat/attempts/{id}/chat : arbitre ∥ patient, persistance, blocage."""
import asyncio
import os
import time
from datetime import datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import chat_routes
from models import (
    Attachment, Attempts, ChatIn, ChatRole, ClinicalCase, Message,
    ModerationEvent, StationType, User,
)
from patient_agent import AgentEvent, PatientAgentResult

ALLOW = {
    "category": "CLINICAL_QUESTION", "tone": "NEUTRAL",
    "exam": {"requested": False, "label": None, "confidence": None},
    "safety": {"allow_to_transcript": True, "redact": False, "redacted_text": None},
}
BLOCK = {
    "category": "ABUSIVE", "tone": "INSULTING",
    "exam": {"requested": False, "label": None, "confidence": None},
    "safety": {"allow_to_transcript": False, "redact": True, "redacted_text": "[REDACTED]"},
}


@pytest.fixture
def session():
    """SQLite en mémoire par défaut ; TEST_DATABASE_URL=postgresql://... pour tester
    sur une base PostgreSQL migrée (chaque test est annulé par rollback)."""
    url = os.getenv("TEST_DATABASE_URL")
    if url:
        engine = create_engine(url)
        with engine.connect() as conn:
            outer = conn.begin()
            with Session(bind=conn, join_transaction_mode="create_savepoint") as s:
                yield s
            outer.rollback()
        engine.dispose()
        return
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


@pytest.fixture
def world(session, monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "vllm")
    monkeypatch.delenv("PATIENT_AGENT_ENABLED", raising=False)

    user = User(username="etu", hashed_password="x")
    session.add(user)
    session.commit()
    case = ClinicalCase(
        title="Douleur thoracique", created_by=user.id, station_type=StationType.patient_interview,
        student_instructions="Interrogez le patient", scenario_context="SCA",
        patient_prompt="Tu es Mr. Dupont.", duration_seconds=600,
        exam_findings=[{"id": "constantes", "label": "Constantes vitales", "findings": "PA 158/94 mmHg"}],
    )
    session.add(case)
    session.commit()
    att = Attachment(
        case_id=case.id, filename="ecg.png", stored_filename="x.png", display_name="ECG 18 dérivations",
        kind="image", mime_type="image/png", size_bytes=10, file_path="x.png", file_url="/files/x.png",
        trigger_keywords="ecg",
    )
    attempt = Attempts(user_id=user.id, case_id=case.id, created_at=datetime.utcnow(),
                       expires_at=datetime.utcnow() + timedelta(minutes=10))
    session.add(att)
    session.add(attempt)
    session.commit()
    return {"user": user, "case": case, "attachment": att, "attempt": attempt}


def messages(session, attempt_id):
    stmt = select(Message).where(Message.attempt_id == attempt_id).order_by(Message.created_at)
    return session.exec(stmt).all()


def events(session, attempt_id):
    return session.exec(select(ModerationEvent).where(ModerationEvent.attempt_id == attempt_id)).all()


async def send(session, world, text):
    return await chat_routes.chat(world["attempt"].id, ChatIn(message=text), session=session, user=world["user"])


@pytest.mark.asyncio
async def test_allowed_message_persists_reply_examiner_notes_and_flags(session, world, monkeypatch):
    captured = {}

    async def fake_agent(**kwargs):
        captured.update(kwargs)
        ctx = kwargs["ctx"]
        return PatientAgentResult(reply="D'accord, allez-y.", events=[
            AgentEvent("exam_findings", {"findings": ctx.exam_findings}),
            AgentEvent("document", {"document": ctx.documents[0]}),
            AgentEvent("flag", {"category": "HORS_SUJET", "severity": "faible", "detail": "blague"}),
        ])

    monkeypatch.setattr(chat_routes, "run_patient_agent", fake_agent)
    monkeypatch.setattr(chat_routes, "classify_student_message_vllm_arbiter", lambda names, msg: ALLOW)

    out = await send(session, world, "Je prends votre tension et je fais un ECG")

    assert out.blocked is False
    assert out.patient_reply == "D'accord, allez-y."
    att_id = str(world["attachment"].id)
    assert out.attachments == [att_id]
    assert [(n.kind, n.title) for n in out.examiner_notes] == [
        ("exam_findings", "Constantes vitales"), ("document", "ECG 18 dérivations"),
    ]
    assert out.examiner_notes[1].file_url == f"/attachments/download/{att_id}"

    rows = messages(session, world["attempt"].id)
    assert [r.role for r in rows] == [ChatRole.student, ChatRole.patient, ChatRole.examiner, ChatRole.examiner]
    assert rows[2].content == "Examen clinique – Constantes vitales : PA 158/94 mmHg"
    assert rows[3].content == "Document affiché – ECG 18 dérivations"
    assert str(rows[3].attachment_id) == att_id

    evts = events(session, world["attempt"].id)
    assert [(e.source, e.category, e.action) for e in evts] == [("patient_agent", "HORS_SUJET", "flagged")]
    assert evts[0].message_id == rows[0].id

    # Le patient ne reçoit que l'historique étudiant/patient
    assert captured["history"] == []

    # Rechargement de la conversation : rôle examinateur + document + type MIME
    listed = chat_routes.get_messages(world["attempt"].id, session=session, user=world["user"])
    assert [m["role"] for m in listed] == ["student", "patient", "examiner", "examiner"]
    assert listed[3]["attachment_id"] == att_id
    assert listed[3]["attachment_mime_type"] == "image/png"
    assert listed[2]["attachment_mime_type"] is None


@pytest.mark.asyncio
async def test_station_state_and_history_on_next_turn(session, world, monkeypatch):
    aid = world["attempt"].id
    session.add(Message(attempt_id=aid, role=ChatRole.system, content="Consignes"))
    session.add(Message(attempt_id=aid, role=ChatRole.student, content="Bonjour"))
    session.add(Message(attempt_id=aid, role=ChatRole.patient, content="Bonjour docteur"))
    session.add(Message(attempt_id=aid, role=ChatRole.examiner, content="Examen clinique – Constantes vitales : PA 158/94"))
    session.commit()
    captured = {}

    async def fake_agent(**kwargs):
        captured.update(kwargs)
        return PatientAgentResult(reply="Oui.")

    monkeypatch.setattr(chat_routes, "run_patient_agent", fake_agent)
    monkeypatch.setattr(chat_routes, "classify_student_message_vllm_arbiter", lambda names, msg: ALLOW)
    await send(session, world, "Vous fumez ?")

    assert captured["history"] == [
        {"role": "student", "content": "Bonjour"}, {"role": "patient", "content": "Bonjour docteur"},
    ]
    assert captured["station_state"] == ["Examen clinique – Constantes vitales"]


@pytest.mark.asyncio
async def test_blocked_message_cancels_patient_and_stores_nothing_in_transcript(session, world, monkeypatch):
    state = {"cancelled": False}

    async def slow_agent(**kwargs):
        try:
            await asyncio.sleep(10)
        except asyncio.CancelledError:
            state["cancelled"] = True
            raise
        return PatientAgentResult(reply="ne doit jamais sortir")

    def arbiter(names, msg):
        time.sleep(0.05)
        return BLOCK

    monkeypatch.setattr(chat_routes, "run_patient_agent", slow_agent)
    monkeypatch.setattr(chat_routes, "classify_student_message_vllm_arbiter", arbiter)

    started = time.perf_counter()
    out = await send(session, world, "espèce de gros ...")
    assert time.perf_counter() - started < 2

    assert out.blocked is True
    assert "bloqué" in out.patient_reply
    assert state["cancelled"] is True
    assert messages(session, world["attempt"].id) == []
    evts = events(session, world["attempt"].id)
    assert len(evts) == 1
    assert (evts[0].source, evts[0].action, evts[0].category) == ("arbiter", "blocked", "ABUSIVE")
    assert evts[0].student_message == "espèce de gros ..."


@pytest.mark.asyncio
async def test_arbiter_and_patient_run_in_parallel(session, world, monkeypatch):
    async def agent(**kwargs):
        await asyncio.sleep(0.4)
        return PatientAgentResult(reply="J'ai mal.")

    def arbiter(names, msg):
        time.sleep(0.4)  # appel bloquant, exécuté dans un thread
        return ALLOW

    monkeypatch.setattr(chat_routes, "run_patient_agent", agent)
    monkeypatch.setattr(chat_routes, "classify_student_message_vllm_arbiter", arbiter)

    started = time.perf_counter()
    out = await send(session, world, "Où avez-vous mal ?")
    elapsed = time.perf_counter() - started
    assert out.patient_reply == "J'ai mal."
    assert elapsed < 0.7, f"séquentiel ? {elapsed:.2f}s"


@pytest.mark.asyncio
async def test_aggressive_tone_is_flagged_but_kept(session, world, monkeypatch):
    async def agent(**kwargs):
        return PatientAgentResult(reply="Pourquoi vous me parlez comme ça ?")

    aggressive = {**ALLOW, "tone": "AGGRESSIVE"}
    monkeypatch.setattr(chat_routes, "run_patient_agent", agent)
    monkeypatch.setattr(chat_routes, "classify_student_message_vllm_arbiter", lambda names, msg: aggressive)

    out = await send(session, world, "Répondez vite, j'ai pas que ça à faire.")
    assert out.blocked is False
    assert len(messages(session, world["attempt"].id)) == 2
    evts = events(session, world["attempt"].id)
    assert [(e.source, e.severity, e.action) for e in evts] == [("arbiter", "AGGRESSIVE", "flagged")]


@pytest.mark.asyncio
async def test_agent_failure_returns_502_and_stores_nothing(session, world, monkeypatch):
    async def broken(**kwargs):
        raise ConnectionError("vLLM injoignable")

    monkeypatch.setattr(chat_routes, "run_patient_agent", broken)
    monkeypatch.setattr(chat_routes, "classify_student_message_vllm_arbiter", lambda names, msg: ALLOW)

    with pytest.raises(chat_routes.HTTPException) as exc:
        await send(session, world, "Bonjour")
    assert exc.value.status_code == 502
    assert messages(session, world["attempt"].id) == []


@pytest.mark.asyncio
async def test_legacy_provider_uses_keyword_matching(session, world, monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "gemini")

    async def must_not_be_called(**kwargs):
        raise AssertionError("l'agent ne doit pas être appelé en mode legacy")

    monkeypatch.setattr(chat_routes, "run_patient_agent", must_not_be_called)
    monkeypatch.setattr(chat_routes, "generate_patient_reply", lambda **kw: "D'accord.")
    monkeypatch.setattr(chat_routes, "classify_student_message_vllm_arbiter", lambda names, msg: ALLOW)

    out = await send(session, world, "Je vous fais un ECG")
    assert out.patient_reply == "D'accord."
    assert out.attachments == [str(world["attachment"].id)]
