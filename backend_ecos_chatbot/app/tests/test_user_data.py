"""Données personnelles (RGPD) : export, suppression d'une tentative ou du compte, purge."""
from datetime import datetime, timedelta

import pytest
import pytest_asyncio
from sqlmodel import select

from models import (
    Attachment, Attempts, ClinicalCase, EvaluationItemResult, EvaluationResult, Message, ModerationEvent,
    StationType, User, UserRole,
)


@pytest.fixture
def data(session):
    """Un enseignant auteur d'une station, un étudiant avec une tentative corrigée et signalée."""
    from auth import get_password_hash

    prof = User(username="prof", hashed_password=get_password_hash("prof-secret-1"), role=UserRole.teacher)
    etu = User(username="etu", hashed_password=get_password_hash("etu-secret-1"), full_name="Jeanne Martin")
    session.add(prof)
    session.add(etu)
    session.commit()
    case = ClinicalCase(title="Dyspnée", created_by=prof.id, station_type=StationType.patient_interview,
                        student_instructions="-", scenario_context="-", patient_prompt="-", duration_seconds=600)
    session.add(case)
    session.commit()
    doc = Attachment(case_id=case.id, filename="radio.png", stored_filename="r.png", display_name="Radio",
                     kind="image", mime_type="image/png", size_bytes=1, file_path="r.png", file_url="/x")
    session.add(doc)
    session.commit()
    attempts = []
    for days, is_test in ((800, False), (800, True), (10, False)):
        attempts.append(_attempt(session, etu, case, doc, days, is_test))
    return {"prof": prof, "etu": etu, "case": case, "doc": doc, "attempts": attempts}


def _attempt(session, user, case, doc, days_ago, is_test=False):
    start = datetime.now() - timedelta(days=days_ago)
    attempt = Attempts(user_id=user.id, case_id=case.id, created_at=start, is_completed=True, is_test=is_test,
                       completed_at=start + timedelta(minutes=8))
    session.add(attempt)
    session.commit()
    msg = Message(attempt_id=attempt.id, role="student", content="Bonjour, je suis l'étudiante.")
    session.add(msg)
    session.add(Message(attempt_id=attempt.id, role="examiner", content="Radio", attachment_id=doc.id))
    session.commit()
    session.add(ModerationEvent(attempt_id=attempt.id, message_id=msg.id, source="arbitre", category="OFF_TOPIC",
                                action="flagged"))
    result = EvaluationResult(attempt_id=attempt.id, case_id=case.id, user_id=user.id, points_obtained=12.0,
                              points_possible=20.0, evaluation_data={"evaluation": {"score_20": 12.0}})
    session.add(result)
    session.commit()
    session.add(EvaluationItemResult(evaluation_result_id=result.id, attempt_id=attempt.id, case_id=case.id,
                                     user_id=user.id, edn_code="", item_name="Se présente", points_obtained=1,
                                     points_possible=1, justification="ok", evaluated_at=datetime.now()))
    session.commit()
    return attempt


def _count(session, model, attempt_ids):
    return len([r for r in session.exec(select(model)).all() if r.attempt_id in attempt_ids])


@pytest_asyncio.fixture
async def client(session, data):
    import httpx
    from fastapi import FastAPI

    import user_routes
    from auth import get_current_user
    from db import get_session

    app = FastAPI()
    app.include_router(user_routes.router, prefix="/api/users")
    current = {"user": data["etu"]}
    app.dependency_overrides[get_session] = lambda: session
    app.dependency_overrides[get_current_user] = lambda: current["user"]
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        c.as_user = lambda name: current.__setitem__("user", data[name])
        yield c


@pytest.mark.asyncio
async def test_export_contains_everything_about_me(client, data):
    r = await client.get("/api/users/me/export")
    assert r.status_code == 200
    assert "attachment" in r.headers["content-disposition"]
    body = r.json()
    assert body["compte"]["identifiant"] == "etu" and body["compte"]["nom"] == "Jeanne Martin"
    assert "hashed_password" not in r.text and "$argon2" not in r.text
    assert len(body["tentatives"]) == 3
    first = body["tentatives"][0]
    assert first["station"] == "Dyspnée" and first["correction"]["score_20"] == 12.0
    assert first["messages"][0]["contenu"].startswith("Bonjour")
    assert first["signalements"][0]["categorie"] == "OFF_TOPIC"


@pytest.mark.asyncio
async def test_delete_one_attempt(client, session, data):
    target = data["attempts"][2]
    client.as_user("prof")
    assert (await client.delete(f"/api/users/me/attempts/{target.id}")).status_code == 404   # pas la sienne
    client.as_user("etu")
    r = await client.delete(f"/api/users/me/attempts/{target.id}")
    assert r.status_code == 200, r.text
    ids = {target.id}
    for model in (Message, EvaluationResult, EvaluationItemResult, ModerationEvent):
        assert _count(session, model, ids) == 0
    assert session.get(Attempts, target.id) is None
    assert session.get(Attachment, data["doc"].id) is not None     # le document de la station reste
    assert len(session.exec(select(Attempts)).all()) == 2


@pytest.mark.asyncio
async def test_delete_account(client, session, data):
    r = await client.request("DELETE", "/api/users/me", json={"password": "pas-le-bon"})
    assert r.status_code == 403
    assert session.get(User, data["etu"].id) is not None

    # Un auteur de stations ne peut pas supprimer son compte lui-même
    client.as_user("prof")
    r = await client.request("DELETE", "/api/users/me", json={"password": "prof-secret-1"})
    assert r.status_code == 409 and "transférer" in r.json()["detail"]

    client.as_user("etu")
    r = await client.request("DELETE", "/api/users/me", json={"password": "etu-secret-1"})
    assert r.status_code == 204
    session.expire_all()
    assert session.exec(select(User).where(User.username == "etu")).first() is None
    assert session.exec(select(Attempts)).all() == []
    assert session.exec(select(Message)).all() == []
    assert session.exec(select(EvaluationResult)).all() == []
    assert session.get(ClinicalCase, data["case"].id) is not None


def test_purge_old_attempts(session, data):
    from user_data import purge_attempts

    old, old_test, recent = data["attempts"]
    two_years = datetime.now() - timedelta(days=730)
    assert purge_attempts(session, two_years, include_tests=False) == 1
    assert session.get(Attempts, old.id) is None
    assert session.get(Attempts, old_test.id) is not None and session.get(Attempts, recent.id) is not None
    assert purge_attempts(session, two_years) == 1
    assert [a.id for a in session.exec(select(Attempts)).all()] == [recent.id]
    assert _count(session, Message, {old.id, old_test.id}) == 0


def test_purge_script_arguments(capsys):
    from scripts import purge_donnees

    with pytest.raises(SystemExit):
        purge_donnees.main([])                  # durée obligatoire
    with pytest.raises(SystemExit):
        purge_donnees.main(["--mois", "0"])
