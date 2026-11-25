"""Formats de station des ECOS nationaux : sans interlocuteur, documents de vignette,
échelles d'attitude et note /20. Stations fictives (aucun contenu de livre)."""
import pytest

from case_sheet import AttitudeScale, CaseSheet, Fact, GridItem, StationDocument, check_sheet, compile_case
from scoring import score_evaluation


def ecg_sheet(attachment_id=None) -> CaseSheet:
    """Station fictive sans interlocuteur : interprétation d'un tracé."""
    sheet = CaseSheet()
    s = sheet.station
    s.title, s.domain, s.interlocutor = "Lecture d'un tracé", "iconographie", "aucun"
    s.student_instructions = "Interprétez le tracé (document 1) et proposez un diagnostic."
    s.duration_minutes = 8
    s.documents = [StationDocument(label="Document 1 : tracé", attachment_id=attachment_id)]
    sheet.correction.expected_diagnosis = "Tracé fictif normal"
    sheet.correction.grid = [GridItem(id="i1", criterion="Annonce sa méthode de lecture"),
                             GridItem(id="i2", criterion="Conclut à un tracé normal")]
    sheet.correction.scales = [AttitudeScale(id="synthese", label="Aptitude à faire la synthèse des données",
                                             levels=["a", "b", "c", "d", "e"]),
                               AttitudeScale(id="non_verbale", label="Communication non verbale")]
    return sheet


def test_no_interlocutor_compiles_without_patient():
    c = compile_case(ecg_sheet("x"))
    assert c["interlocutor"] == "aucun" and c["patient_prompt"] is None
    assert c["station_type"] == "exam_analysis"
    assert "sans interlocuteur" in c["student_instructions"]
    assert c["documents"] == [{"id": c["documents"][0]["id"], "label": "Document 1 : tracé", "attachment_id": "x"}]
    assert [s["id"] for s in c["scales"]] == ["synthese", "non_verbale"]
    assert c["scales"][1]["observable"] is False and len(c["scales"][1]["levels"]) == 5
    assert "Station sans interlocuteur" in c["scenario_context"]
    # Ni faits ni personnage exigés ; document sans fichier signalé
    issues = check_sheet(ecg_sheet())
    assert not [i for i in issues if i.level == "erreur"]
    assert any(i.field == "station.documents[0]" for i in issues)
    assert not any(i.field.startswith(("facts", "patient")) for i in issues)


def test_education_station_with_patient_has_no_interview_warnings():
    sheet = CaseSheet()
    sheet.station.title, sheet.station.domain = "Conseils après une hospitalisation", "education_prevention"
    sheet.station.student_instructions = "Expliquez les règles hygiéno-diététiques."
    sheet.patient.age = 70
    sheet.facts = [Fact(category="mode_de_vie", label="Tabac", patient_words="Je fume un paquet par jour.",
                        asked_about="le tabac")]
    sheet.correction.grid = [GridItem(criterion="Propose une aide au sevrage tabagique")]
    issues = check_sheet(sheet)
    assert not [i for i in issues if i.level == "erreur"]
    assert not any(i.field.startswith("correction.grid") for i in issues)       # pas de lien aux faits exigé
    assert not any("signes négatifs" in i.message for i in issues)
    assert compile_case(sheet)["station_type"] == "patient_interview"
    sheet.station.domain = "procedure"
    assert "décrivez à voix haute chaque geste" in compile_case(sheet)["student_instructions"]


def test_score_on_20_with_scales():
    grid = {"items": [{"id": "i1", "points": 1}, {"id": "i2", "points": 1}, {"id": "i3", "points": 2}],
            "scales": compile_case(ecg_sheet())["scales"], "global_rating": True, "attitude_weight": 0.25}
    llm = {"evaluation": {
        "items": [{"item_id": "i1", "points_awarded": 1, "justification": "« ... »"},
                  {"item_id": "i3", "points_awarded": 5, "justification": "« ... »"},   # borné à 2
                  {"item_id": "inconnu", "points_awarded": 1}],
        "total_score": 99, "general_feedback": "Bien",
        "scales": [{"scale_id": "synthese", "level": 3, "justification": "claire"},
                   {"scale_id": "non_verbale", "level": 0, "justification": "?"}],      # non observable : ignorée
        "global_performance": {"level": 7, "justification": "très bien"},             # borné à 4
    }}
    ev = score_evaluation(llm, grid)["evaluation"]
    assert (ev["items_score"], ev["items_possible"]) == (3.0, 4.0)
    assert [i["item_id"] for i in ev["items"]] == ["i1", "i2", "i3"] and ev["items"][1]["points_awarded"] == 0
    assert [(s["scale_id"], s["level"]) for s in ev["scales"]] == [("synthese", 3), ("non_verbale", None)]
    # 20 × (0,75 × 3/4 + 0,25 × 3/4) = 15
    assert ev["score_20"] == 15.0 and ev["percentage"] == 75.0
    assert ev["global_performance"]["level"] == 4 and ev["global_performance"]["level_name"] == "remarquable"

    # Sans échelle cotée : la note ne dépend que des items
    ev = score_evaluation({"evaluation": {"items": llm["evaluation"]["items"]}}, {"items": grid["items"]})["evaluation"]
    assert ev["score_20"] == 15.0 and ev["scales"] == [] and ev["global_performance"] is None


@pytest.fixture
def silent_world(session, monkeypatch):
    """Station sans interlocuteur publiée, avec un document de vignette."""
    import uuid
    from datetime import datetime, timedelta

    import case_publishing
    import chat_routes
    from models import Attachment, Attempts, ClinicalCase, User, UserRole
    from contextlib import contextmanager

    @contextmanager
    def test_write_session():
        yield session
    monkeypatch.setattr(chat_routes, "_write_session", test_write_session)

    user = User(username="etu", hashed_password="x", role=UserRole.student)
    session.add(user)
    session.commit()
    case = ClinicalCase(title="t", created_by=user.id, student_instructions="", scenario_context="", duration_seconds=480)
    session.add(case)
    session.flush()
    att = Attachment(id=uuid.uuid4(), case_id=case.id, filename="trace.png", stored_filename="t.png",
                     display_name="Tracé", kind="image", mime_type="image/png", size_bytes=1,
                     file_path="images/t.png", file_url="/files/images/t.png")
    session.add(att)
    session.flush()
    version = case_publishing.publish(session, case, ecg_sheet(str(att.id)), user.id)
    attempt = Attempts(user_id=user.id, case_id=case.id, created_at=datetime.utcnow(), case_version_id=version.id,
                       expires_at=datetime.utcnow() + timedelta(minutes=8))
    session.add(attempt)
    session.flush()
    chat_routes.add_start_messages(session, attempt, version, case)
    session.commit()
    return {"user": user, "case": case, "attempt": attempt, "attachment": att}


@pytest.mark.asyncio
async def test_silent_station_turn(session, silent_world, monkeypatch):
    from sqlmodel import select

    import chat_routes
    from models import ChatIn, ChatRole, Message

    async def no_patient(*a, **k):
        raise AssertionError("aucun patient ne doit répondre")
    monkeypatch.setattr(chat_routes, "stream_patient_agent", no_patient)
    monkeypatch.setattr(chat_routes, "arbitrate", no_patient)

    attempt, user = silent_world["attempt"], silent_world["user"]
    # Document de la vignette affiché dès le début
    start = session.exec(select(Message).where(Message.attempt_id == attempt.id).order_by(Message.created_at)).all()
    assert [m.role for m in start] == [ChatRole.system, ChatRole.examiner]
    assert start[1].attachment_id == silent_world["attachment"].id and "Document 1" in start[1].content
    assert "sans interlocuteur" in start[0].content

    out = await chat_routes.chat(attempt.id, ChatIn(message="Le rythme est sinusal."), session, user)
    assert out.silent and out.patient_reply == ""
    rows = session.exec(select(Message).where(Message.attempt_id == attempt.id).order_by(Message.created_at)).all()
    assert [m.role for m in rows][-1] == ChatRole.student and rows[-1].content == "Le rythme est sinusal."

    info = chat_routes.get_case_info(attempt.id, session, user)
    assert info["interlocutor"] == "aucun" and info["domain"] == "iconographie"


def test_written_answer_is_submitted_once(session, silent_world):
    """Station sans interlocuteur : réponse complète rendue en une fois, station terminée."""
    from fastapi import HTTPException
    from pydantic import ValidationError
    from sqlmodel import select

    import chat_routes
    from models import MAX_WRITTEN_ANSWER_CHARS, AnswerIn, ChatRole, Message

    attempt, user = silent_world["attempt"], silent_world["user"]
    info = chat_routes.get_case_info(attempt.id, session, user)
    assert info["student_instructions"].startswith("Interprétez le tracé")
    assert "rendez-la en une fois" in info["student_instructions"]

    long_answer = "Rythme sinusal régulier. " * 200          # bien plus long qu'un message de chat
    assert 2000 < len(long_answer) < MAX_WRITTEN_ANSWER_CHARS
    out = chat_routes.submit_written_answer(attempt.id, AnswerIn(answer=long_answer), session, user)
    assert out["status"] == "ok"
    session.refresh(attempt)
    assert attempt.is_completed and attempt.completed_at is not None
    rows = session.exec(select(Message).where(Message.attempt_id == attempt.id, Message.role == ChatRole.student)).all()
    assert len(rows) == 1 and rows[0].content == long_answer.strip()

    with pytest.raises(HTTPException) as exc:      # une seule fois
        chat_routes.submit_written_answer(attempt.id, AnswerIn(answer="Encore"), session, user)
    assert exc.value.status_code == 409
    with pytest.raises(ValidationError):
        AnswerIn(answer="x" * (MAX_WRITTEN_ANSWER_CHARS + 1))


def test_written_answer_deadline(session, silent_world):
    """Rendue juste après la fin du temps (envoi automatique) : acceptée ; trop tard : refusée."""
    from datetime import datetime, timedelta

    from fastapi import HTTPException

    import chat_routes
    from models import AnswerIn

    attempt, user = silent_world["attempt"], silent_world["user"]
    attempt.expires_at = datetime.utcnow() - timedelta(seconds=10)
    session.add(attempt)
    session.commit()
    assert chat_routes.submit_written_answer(attempt.id, AnswerIn(answer="Tracé normal."), session, user)["status"] == "ok"

    attempt.is_completed, attempt.completed_at = False, None
    attempt.expires_at = datetime.utcnow() - timedelta(seconds=chat_routes.ANSWER_GRACE_SECONDS + 30)
    session.add(attempt)
    session.commit()
    with pytest.raises(HTTPException) as exc:
        chat_routes.submit_written_answer(attempt.id, AnswerIn(answer="Trop tard."), session, user)
    assert exc.value.status_code == 410
    session.refresh(attempt)
    assert attempt.is_completed


def test_written_answer_refused_for_conversation_stations(session, world):
    from fastapi import HTTPException

    import chat_routes
    from models import AnswerIn

    with pytest.raises(HTTPException) as exc:
        chat_routes.submit_written_answer(world["attempt"].id, AnswerIn(answer="Bonjour"), session, world["user"])
    assert exc.value.status_code == 409


def test_silent_station_evaluation(session, silent_world, monkeypatch):
    import evaluation_routes
    from models import ChatRole, Message

    attempt, user = silent_world["attempt"], silent_world["user"]
    session.add(Message(attempt_id=attempt.id, role=ChatRole.student, content="Je conclus à un tracé normal."))
    attempt.is_completed = True
    session.add(attempt)
    session.commit()

    seen = {}

    def fake_llm(transcript, evaluation_grid, case_context):
        seen.update(transcript=transcript, grid=evaluation_grid)
        return {"evaluation": {"items": [{"item_id": "i1", "points_awarded": 0, "citation": "", "justification": "absent"},
                                         {"item_id": "i2", "points_awarded": 1, "justification": "« normal »"}],
                               "scales": [{"scale_id": "synthese", "level": 2, "justification": "ok"}],
                               "global_performance": {"level": 2, "justification": "ok"},
                               "general_feedback": "ok"}}
    monkeypatch.setattr(evaluation_routes, "evaluate_attempt_with_llm", fake_llm)

    out = evaluation_routes.evaluate_attempt(attempt.id, session, user)
    assert seen["transcript"].startswith("[STATION SANS INTERLOCUTEUR]")
    assert "EXAMINATEUR: Document affiché – Document 1 : tracé" in seen["transcript"]
    assert [s["id"] for s in seen["grid"]["scales"]] == ["synthese", "non_verbale"] and seen["grid"]["global_rating"]
    ev = out["evaluation"]
    # 20 × (0,75 × 1/2 + 0,25 × 2/4) = 10
    assert ev["score_20"] == 10.0 and ev["global_performance"]["level"] == 2

    from models import EvaluationResult
    from sqlmodel import select
    saved = session.exec(select(EvaluationResult).where(EvaluationResult.attempt_id == attempt.id)).one()
    assert (saved.points_obtained, saved.points_possible) == (10.0, 20.0)


def test_teaching_only_after_the_station(session, silent_world):
    import evaluation_routes
    from fastapi import HTTPException
    from models import CaseVersion

    attempt, user = silent_world["attempt"], silent_world["user"]
    version = session.get(CaseVersion, attempt.case_version_id)
    sheet = dict(version.sheet)
    sheet["correction"] = {**sheet["correction"], "teaching": {"objectives": ["Lire un tracé"], "comments": "Méthode."}}
    version.sheet = sheet
    session.add(version)
    session.commit()

    with pytest.raises(HTTPException) as exc:
        evaluation_routes.get_teaching(attempt.id, session, user)
    assert exc.value.status_code == 400
    attempt.is_completed = True
    session.add(attempt)
    session.commit()
    out = evaluation_routes.get_teaching(attempt.id, session, user)
    assert out["objectives"] == ["Lire un tracé"] and out["comments"] == "Méthode." and out["model_script"] == ""


@pytest.mark.asyncio
async def test_editor_preview_of_a_silent_station(session):
    import httpx
    from fastapi import FastAPI

    import authoring_routes
    from auth import get_current_user
    from db import get_session
    from models import ClinicalCase, User, UserRole

    prof = User(username="prof", hashed_password="x", role=UserRole.teacher)
    session.add(prof)
    session.commit()
    case = ClinicalCase(title="t", created_by=prof.id, student_instructions="", scenario_context="",
                        duration_seconds=480, sheet=ecg_sheet().model_dump(mode="json"))
    session.add(case)
    session.commit()
    app = FastAPI()
    app.include_router(authoring_routes.router, prefix="/authoring")
    app.dependency_overrides[get_session] = lambda: session
    app.dependency_overrides[get_current_user] = lambda: prof
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get(f"/authoring/cases/{case.id}")
        assert r.status_code == 200, r.text
        assert r.json()["preview"]["patient_prompt"] is None


def colleague_sheet() -> CaseSheet:
    """Station fictive avec un professionnel de santé simulé (appel d'un collègue)."""
    sheet = CaseSheet()
    s = sheet.station
    s.title, s.domain, s.interlocutor = "Appel au médecin de garde", "communication_interprofessionnelle", "professionnel"
    s.student_instructions = "Appelez le médecin de garde pour organiser la suite."
    s.student_role = "l'interne des urgences d'un autre hôpital"
    sheet.patient.occupation = "médecin de garde du service fictif"
    sheet.patient.emotional_state = "Pressé mais disponible"
    sheet.patient.spontaneous_questions = ["Que montre l'examen ?", "Que proposes-tu ?"]
    sheet.facts = [Fact(category="contexte", label="Lits disponibles", patient_words="Il me reste un lit.",
                        asked_about="les lits disponibles")]
    sheet.correction.grid = [GridItem(id="i1", criterion="Se présente"), GridItem(id="i2", criterion="Formule sa demande")]
    return sheet


def test_professional_interlocutor_compiles_as_a_colleague():
    c = compile_case(colleague_sheet())
    assert c["interlocutor"] == "professionnel" and c["interlocutor_label"] == "Médecin de garde du service fictif"
    prompt = c["patient_prompt"]
    assert prompt.startswith("Tu es médecin de garde du service fictif.")
    assert "La personne qui s'adresse à toi est l'interne des urgences d'un autre hôpital." in prompt
    assert "« Que montre l'examen ? »" in prompt and "tu ne fais pas son travail" in prompt
    assert "Tu ne connais pas ton diagnostic" not in prompt            # règles du patient absentes
    assert "professionnel de santé simulé" in c["scenario_context"]
    assert not [i for i in check_sheet(colleague_sheet()) if i.level == "erreur"]
    sheet = colleague_sheet()
    sheet.patient.occupation = ""
    assert any(i.field == "patient.occupation" and i.level == "erreur" for i in check_sheet(sheet))
    # Vocabulaire médical permis : pas d'alerte « jargon »
    sheet = colleague_sheet()
    sheet.facts[0].patient_words = "Bradycardie à 40 avec un BAV complet."
    assert not any("Jargon" in i.message for i in check_sheet(sheet))


def test_professional_role_rules_and_transcript():
    from types import SimpleNamespace

    from evaluation_routes import build_evaluation_transcript
    from models import ChatRole
    from patient_agent import CaseToolContext, build_agent_system_instruction

    ctx = CaseToolContext(documents=[], exam_findings=[])
    pro = build_agent_system_instruction("Tu es cardiologue de garde.", ctx, role="professionnel")
    assert pro.startswith("Tu es un professionnel de santé simulé") and "Tu es cardiologue de garde." in pro
    assert "Tu incarnes le patient" not in pro
    patient = build_agent_system_instruction("Tu es Jean.", ctx)
    assert patient.startswith("Tu incarnes le patient")

    msg = lambda role, content: SimpleNamespace(role=role, content=content, modality="text",
                                                interrupted_by=None, spoken_content=None)
    transcript, _ = build_evaluation_transcript(
        [msg(ChatRole.student, "Bonjour, interne des urgences."), msg(ChatRole.patient, "Je t'écoute.")],
        professional="Cardiologue de garde")
    assert transcript == "ÉTUDIANT: Bonjour, interne des urgences.\n\nPROFESSIONNEL DE SANTÉ (Cardiologue de garde): Je t'écoute."
