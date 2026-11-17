"""Atelier de création de cas : brouillon, aperçu, publication versionnée, test enseignant."""
import pytest
import pytest_asyncio

from case_examples import dupont_sheet


@pytest.fixture
def people(session):
    from models import EDNItem, User, UserRole

    users = {
        "prof": User(username="prof", hashed_password="x", role=UserRole.teacher),
        "autre_prof": User(username="autre", hashed_password="x", role=UserRole.teacher),
        "admin": User(username="admin", hashed_password="x", role=UserRole.admin),
        "etu": User(username="etu", hashed_password="x", role=UserRole.student),
    }
    for u in users.values():
        session.add(u)
    session.add(EDNItem(number=339, title="Syndromes coronariens aigus"))
    session.commit()
    return users


@pytest_asyncio.fixture
async def client(session, people, monkeypatch):
    """Client HTTP ; `client.as_user("prof")` change l'utilisateur connecté."""
    import httpx
    from fastapi import FastAPI

    import authoring_routes
    import chat_routes
    import evaluation_routes
    import user_routes
    from auth import get_current_user
    from db import get_session

    app = FastAPI()
    app.include_router(authoring_routes.router, prefix="/authoring")
    app.include_router(chat_routes.router, prefix="/chat")
    app.include_router(evaluation_routes.router, prefix="/evaluation")
    app.include_router(user_routes.router, prefix="/api/users")
    current = {"user": people["prof"]}
    app.dependency_overrides[get_session] = lambda: session
    app.dependency_overrides[get_current_user] = lambda: current["user"]

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        c.as_user = lambda name: current.__setitem__("user", people[name])
        yield c


async def _new_case(client, sheet=None):
    r = await client.post("/authoring/cases", json={"title": "Douleur thoracique"})
    assert r.status_code == 200, r.text
    case_id = r.json()["id"]
    if sheet is not None:
        r = await client.put(f"/authoring/cases/{case_id}/sheet", json=sheet.model_dump(mode="json"))
        assert r.status_code == 200, r.text
    return case_id


@pytest.mark.asyncio
async def test_draft_preview_and_checks(client):
    r = await client.post("/authoring/cases", json={"title": "Douleur thoracique"})
    body = r.json()
    assert body["status"] == "draft" and body["legacy"] is False
    assert body["sheet"]["station"]["title"] == "Douleur thoracique"
    # Fiche vide : erreurs bloquantes signalées dès la création
    assert any(i["level"] == "erreur" for i in body["issues"])

    r = await client.put(f"/authoring/cases/{body['id']}/sheet", json=dupont_sheet().model_dump(mode="json"))
    detail = r.json()
    assert not [i for i in detail["issues"] if i["level"] == "erreur"]
    assert detail["preview"]["patient_prompt"].startswith("Tu es Jean Dupont")
    assert detail["preview"]["total_points"] == 20

    r = await client.get("/authoring/cases")
    assert [c["id"] for c in r.json()] == [body["id"]]
    assert r.json()[0]["errors"] == 0


@pytest.mark.asyncio
async def test_roles_and_ownership(client):
    case_id = await _new_case(client, dupont_sheet())

    client.as_user("etu")
    assert (await client.get("/authoring/cases")).status_code == 403

    client.as_user("autre_prof")
    assert (await client.get(f"/authoring/cases/{case_id}")).status_code == 403
    assert (await client.get("/authoring/cases")).json() == []

    client.as_user("admin")
    assert (await client.get(f"/authoring/cases/{case_id}")).status_code == 200
    assert len((await client.get("/authoring/cases")).json()) == 1


@pytest.mark.asyncio
async def test_publish_refused_with_errors(client, session):
    from models import CaseVersion

    case_id = await _new_case(client)
    r = await client.post(f"/authoring/cases/{case_id}/publish")
    assert r.status_code == 422
    assert r.json()["detail"]["issues"]
    assert session.exec(__import__("sqlmodel").select(CaseVersion)).all() == []


@pytest.mark.asyncio
async def test_publish_compiles_runtime_fields(client, session):
    from sqlmodel import select

    from models import CaseEdnLink, ClinicalCase, EvaluationGrid

    case_id = await _new_case(client, dupont_sheet())
    r = await client.post(f"/authoring/cases/{case_id}/publish")
    assert r.status_code == 200, r.text
    assert r.json()["version"]["version"] == 1

    case = session.get(ClinicalCase, case_id)
    assert case.status == "published"
    assert case.title == dupont_sheet().station.title
    assert case.patient_prompt.startswith("Tu es Jean Dupont")
    assert case.duration_seconds == 360
    assert case.voice_id == dupont_sheet().station.voice_id
    grid = session.exec(select(EvaluationGrid).where(EvaluationGrid.case_id == case_id)).one()
    assert grid.total_points == 20 and len(grid.items) == 14
    # Seul l'item 339 existe en base : il est lié, le 230 est ignoré
    assert len(session.exec(select(CaseEdnLink).where(CaseEdnLink.case_id == case_id)).all()) == 1


@pytest.mark.asyncio
async def test_title_clash(client):
    a = await _new_case(client, dupont_sheet())
    assert (await client.post(f"/authoring/cases/{a}/publish")).status_code == 200
    b = await _new_case(client, dupont_sheet())
    r = await client.post(f"/authoring/cases/{b}/publish")
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_attempt_keeps_the_version_it_played(client, session, monkeypatch):
    """Une republication ne change ni le patient ni la grille d'une tentative en cours."""
    import evaluation_routes
    from models import Attempts

    sheet = dupont_sheet()
    case_id = await _new_case(client, sheet)
    await client.post(f"/authoring/cases/{case_id}/publish")

    client.as_user("etu")
    r = await client.post("/chat/attempts", json={"case_id": case_id})
    assert r.status_code == 200, r.text
    attempt_id = r.json()["id"]

    # L'enseignant change l'âge du patient et retire un item de la grille, puis republie
    client.as_user("prof")
    sheet.patient.age = 72
    sheet.correction.grid = sheet.correction.grid[:-1]
    await client.put(f"/authoring/cases/{case_id}/sheet", json=sheet.model_dump(mode="json"))
    r = await client.post(f"/authoring/cases/{case_id}/publish")
    assert r.json()["version"]["version"] == 2

    import chat_routes
    from models import ChatIn
    from uuid import UUID
    attempt = session.get(Attempts, UUID(attempt_id))
    turn = chat_routes._prepare_turn(attempt.id, ChatIn(message="Bonjour"), session, people_user(session, "etu"))
    assert "58 ans" in turn.patient_prompt and "72 ans" not in turn.patient_prompt

    captured = {}

    def fake_eval(transcript, evaluation_grid, case_context):
        captured["grid"] = evaluation_grid
        return {"evaluation": {"items": [], "total_score": 0.0, "total_possible": 20.0,
                               "percentage": 0.0, "general_feedback": ""}}
    monkeypatch.setattr(evaluation_routes, "evaluate_attempt_with_llm", fake_eval)

    client.as_user("etu")
    await client.post(f"/chat/attempts/{attempt_id}/finalize")
    from models import ChatRole, Message
    session.add(Message(attempt_id=attempt.id, role=ChatRole.student, content="Bonjour"))
    session.commit()
    r = await client.post(f"/evaluation/attempts/{attempt_id}/evaluate")
    assert r.status_code == 200, r.text
    assert len(captured["grid"]["items"]) == 14 and captured["grid"]["total_points"] == 20

    # Une nouvelle tentative joue la version 2
    r = await client.post("/chat/attempts", json={"case_id": case_id})
    new = session.get(Attempts, UUID(r.json()["id"]))
    turn = chat_routes._prepare_turn(new.id, ChatIn(message="Bonjour"), session, people_user(session, "etu"))
    assert "72 ans" in turn.patient_prompt


def people_user(session, username):
    from sqlmodel import select

    from models import User
    return session.exec(select(User).where(User.username == username)).one()


@pytest.mark.asyncio
async def test_students_cannot_play_drafts(client):
    case_id = await _new_case(client, dupont_sheet())
    client.as_user("etu")
    assert (await client.post("/chat/attempts", json={"case_id": case_id})).status_code == 404


@pytest.mark.asyncio
async def test_teacher_test_attempt(client, session):
    from uuid import UUID

    import chat_routes
    from models import Attempts, CaseVersion, ChatIn

    case_id = await _new_case(client)
    # Sans aucun fait, il n'y a rien à jouer
    assert (await client.post(f"/authoring/cases/{case_id}/test")).status_code == 422

    sheet = dupont_sheet()
    sheet.station.title = ""     # erreur bloquante pour publier, pas pour tester
    await client.put(f"/authoring/cases/{case_id}/sheet", json=sheet.model_dump(mode="json"))
    r = await client.post(f"/authoring/cases/{case_id}/test")
    assert r.status_code == 200, r.text
    attempt = session.get(Attempts, UUID(r.json()["attempt_id"]))
    version = session.get(CaseVersion, r.json()["version_id"])
    assert attempt.is_test and version.status == "test"
    assert attempt.case_version_id == version.id

    turn = chat_routes._prepare_turn(attempt.id, ChatIn(message="Bonjour"), session, people_user(session, "prof"))
    assert turn.patient_prompt == version.patient_prompt

    # Le brouillon reste un brouillon ; la version de test n'est pas jouée par les étudiants
    detail = (await client.get(f"/authoring/cases/{case_id}")).json()
    assert detail["status"] == "draft"
    assert [v["status"] for v in detail["versions"]] == ["test"]
    assert chat_routes.latest_published_version(session, case_id) is None

    # Les tentatives de test sont exclues des statistiques
    r = await client.get("/api/users/me/stats")
    assert r.status_code == 200, r.text
    assert r.json()["total_attempts"] == 0 and r.json()["cases_attempted"] == []
    r = await client.get("/api/users/me/attempts")
    assert r.status_code == 200, r.text
    assert r.json()["attempts"] == [] and r.json()["stats"]["total_attempts"] == 0


@pytest.mark.asyncio
async def test_reference_situations(client, session):
    from models import ItemSituationLink, StartingSituation

    session.add(StartingSituation(number=161, title="Douleur thoracique"))
    session.add(StartingSituation(number=12, title="Dyspnée"))
    session.add(ItemSituationLink(item_number=339, situation_number=161))
    session.commit()
    r = await client.get("/authoring/reference/situations", params={"items": "339"})
    assert [(s["number"], s["linked"]) for s in r.json()] == [(161, True), (12, False)]
    r = await client.get("/authoring/reference/items")
    assert r.json() == [{"number": 339, "title": "Syndromes coronariens aigus"}]


@pytest.mark.asyncio
async def test_corpus_routes(client, session):
    from pathlib import Path

    from corpus import parse_sfc_chapter, store_chapter

    html = (Path(__file__).parent / "fixtures" / "sfc_chapter_fictif.html").read_text(encoding="utf-8")
    store_chapter(session, parse_sfc_chapter(html, "https://example.org/chapitre-99/"))
    session.commit()

    r = await client.get("/authoring/corpus/search", params={"q": "tabagisme", "items": "999"})
    assert r.status_code == 200 and r.json()[0]["label"].startswith("Item 999")
    r = await client.get("/authoring/corpus/objectives", params={"items": "999"})
    assert [o["rank"] for o in r.json()] == ["A", "A", "B"]

    client.as_user("etu")
    assert (await client.get("/authoring/corpus/search", params={"q": "x"})).status_code == 403


@pytest.mark.asyncio
async def test_peer_review_is_optional(client, session):
    """Statut « à relire » : visible des collègues, relu par un autre enseignant, jamais bloquant."""
    sheet = dupont_sheet()
    case_id = await _new_case(client, sheet)
    detail = (await client.get(f"/authoring/cases/{case_id}")).json()
    assert detail["review"]["status"] is None and detail["can_edit"] and not detail["can_review"]

    # Publiable sans aucune relecture
    assert (await client.post(f"/authoring/cases/{case_id}/publish")).status_code == 200

    # Demande de relecture : réservée à l'auteur ; ne bloque pas une nouvelle publication
    client.as_user("autre_prof")
    assert (await client.post(f"/authoring/cases/{case_id}/review/request")).status_code == 403
    client.as_user("prof")
    r = await client.post(f"/authoring/cases/{case_id}/review/request")
    assert r.json()["review"]["status"] == "a_relire"
    assert (await client.post(f"/authoring/cases/{case_id}/publish")).status_code == 200
    # L'auteur ne se relit pas lui-même
    assert (await client.post(f"/authoring/cases/{case_id}/review", json={"note": "ok"})).status_code == 403

    # Un collègue la voit, la lit, la teste, mais ne la modifie pas
    client.as_user("autre_prof")
    listed = (await client.get("/authoring/cases")).json()
    assert [(c["id"], c["owned"], c["review_status"], c["author"]) for c in listed] == [(case_id, False, "a_relire", "prof")]
    detail = (await client.get(f"/authoring/cases/{case_id}")).json()
    assert not detail["can_edit"] and detail["can_review"]
    assert (await client.put(f"/authoring/cases/{case_id}/sheet", json=sheet.model_dump(mode="json"))).status_code == 403
    assert (await client.post(f"/authoring/cases/{case_id}/publish")).status_code == 403
    assert (await client.post(f"/authoring/cases/{case_id}/test")).status_code == 200

    r = await client.post(f"/authoring/cases/{case_id}/review", json={"note": "Ajouter la question sur le diabète."})
    review = r.json()["review"]
    assert review["status"] == "relue" and review["reviewer"] == "autre"
    assert review["note"] == "Ajouter la question sur le diabète." and not review["changed_since_review"]
    assert (await client.post(f"/authoring/cases/{case_id}/review", json={})).status_code == 409
    # Le relecteur garde l'accès en lecture ; les autres collègues ne la voient plus
    assert (await client.get(f"/authoring/cases/{case_id}")).status_code == 200

    # L'auteur modifie après relecture : signalé
    client.as_user("prof")
    sheet.patient.age = 59
    r = await client.put(f"/authoring/cases/{case_id}/sheet", json=sheet.model_dump(mode="json"))
    assert r.json()["review"]["changed_since_review"] is True

    # Retirer le statut
    r = await client.delete(f"/authoring/cases/{case_id}/review")
    assert r.json()["review"] == {"status": None, "requested_at": None, "reviewer": None, "reviewed_at": None,
                                  "note": None, "changed_since_review": False}
    client.as_user("autre_prof")
    assert (await client.get(f"/authoring/cases/{case_id}")).status_code == 403


@pytest.mark.asyncio
async def test_admin_can_review_own_case(client):
    client.as_user("admin")
    case_id = await _new_case(client, dupont_sheet())
    await client.post(f"/authoring/cases/{case_id}/review/request")
    r = await client.post(f"/authoring/cases/{case_id}/review", json={"note": ""})
    assert r.status_code == 200 and r.json()["review"]["status"] == "relue" and r.json()["review"]["note"] is None
