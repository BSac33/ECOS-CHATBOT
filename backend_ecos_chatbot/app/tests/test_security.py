"""Sécurité : comptes, connexion, origine des requêtes, configuration, pièces jointes."""
import logging
from datetime import datetime, timedelta

import pytest
import pytest_asyncio

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


# ==================== COMPTES ET CONNEXION ====================

@pytest.fixture
def accounts(session):
    from auth import get_password_hash
    from models import User, UserRole

    users = {
        "admin": User(username="admin", hashed_password=get_password_hash("admin-secret-1"), role=UserRole.admin),
        "etu": User(username="etu", hashed_password=get_password_hash("etu-secret-1"), role=UserRole.student),
    }
    for u in users.values():
        session.add(u)
    session.commit()
    return users


@pytest_asyncio.fixture
async def auth_client(session, accounts, monkeypatch):
    """Vraie authentification (cookie), seule la base est remplacée."""
    import httpx
    from fastapi import FastAPI

    import auth
    from db import get_session

    monkeypatch.setattr(auth, "login_throttle", auth.LoginThrottle())
    app = FastAPI()
    app.include_router(auth.router, prefix="/auth")
    app.dependency_overrides[get_session] = lambda: session
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def _login(client, username, password):
    return await client.post("/auth/token", data={"username": username, "password": password})


@pytest.mark.asyncio
async def test_only_admins_create_accounts(auth_client, caplog):
    new = {"username": "nouveau", "password": "motdepasse-123", "role": "teacher"}
    assert (await auth_client.post("/auth/create-user", json=new)).status_code == 401

    assert (await _login(auth_client, "etu", "etu-secret-1")).status_code == 200
    assert (await auth_client.post("/auth/create-user", json=new)).status_code == 403

    auth_client.cookies.clear()
    assert (await _login(auth_client, "admin", "admin-secret-1")).status_code == 200
    with caplog.at_level(logging.INFO):
        r = await auth_client.post("/auth/create-user", json=new)
    assert r.status_code == 201
    assert "motdepasse-123" not in caplog.text
    assert (await auth_client.post("/auth/create-user", json=new)).status_code == 409
    # Mot de passe trop court, identifiant invalide
    assert (await auth_client.post("/auth/create-user", json={**new, "username": "x2", "password": "court"})
            ).status_code == 422
    assert (await auth_client.post("/auth/create-user", json={**new, "username": "a b<script>"})).status_code == 422


@pytest.mark.asyncio
async def test_login_errors_do_not_reveal_accounts(auth_client):
    unknown = await _login(auth_client, "personne", "nimporte-quoi")
    wrong = await _login(auth_client, "etu", "mauvais-mdp")
    assert unknown.status_code == wrong.status_code == 401
    assert unknown.json() == wrong.json()


@pytest.mark.asyncio
async def test_login_throttle(auth_client):
    for _ in range(5):
        assert (await _login(auth_client, "etu", "mauvais-mdp")).status_code == 401
    # Bloqué même avec le bon mot de passe, pour cet identifiant seulement
    assert (await _login(auth_client, "etu", "etu-secret-1")).status_code == 429
    assert (await _login(auth_client, "admin", "admin-secret-1")).status_code == 200


@pytest.mark.asyncio
async def test_disabled_account(auth_client, session, accounts):
    accounts["etu"].is_active = False
    session.add(accounts["etu"])
    session.commit()
    assert (await _login(auth_client, "etu", "etu-secret-1")).status_code == 403


def test_throttle_window_expires(monkeypatch):
    import auth
    throttle = auth.LoginThrottle()
    now = [1000.0]
    monkeypatch.setattr(auth.time, "monotonic", lambda: now[0])
    for _ in range(5):
        throttle.failure("u:etu")
    assert throttle.blocked("u:etu")
    now[0] += throttle.WINDOW + 1
    assert not throttle.blocked("u:etu")
    for _ in range(29):
        throttle.failure("ip:10.0.0.1")
    assert not throttle.blocked("ip:10.0.0.1")
    throttle.failure("ip:10.0.0.1")
    assert throttle.blocked("ip:10.0.0.1")


# ==================== APPLICATION : ORIGINE, SANTÉ, CONFIGURATION ====================

@pytest_asyncio.fixture
async def app_client():
    import httpx

    import main
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_health(app_client):
    r = await app_client.get("/health")
    assert r.status_code == 200 and r.json()["database"] is True


@pytest.mark.asyncio
async def test_cross_site_writes_are_refused(app_client):
    assert (await app_client.post("/auth/logout", headers={"Origin": "https://pirate.example"})).status_code == 403
    assert (await app_client.post("/auth/logout", headers={"Origin": "http://test"})).status_code == 200
    assert (await app_client.post("/auth/logout")).status_code == 200            # CLI, scripts
    assert (await app_client.post("/auth/logout", headers={"Origin": "http://localhost:5173"})).status_code == 200
    # Lecture : jamais bloquée par l'origine
    assert (await app_client.get("/health", headers={"Origin": "https://pirate.example"})).status_code == 200


@pytest.mark.asyncio
async def test_api_docs_hidden_by_default(app_client):
    assert (await app_client.get("/docs")).status_code == 404
    assert (await app_client.get("/openapi.json")).status_code == 404


def test_example_secrets_refused(monkeypatch):
    import main
    monkeypatch.setenv("SECRET_KEY", "changez_moi_par_une_cle_aleatoire")
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        main.check_configuration()
    monkeypatch.setenv("SECRET_KEY", "a" * 64)
    monkeypatch.setenv("DATABASE_URL", "postgresql://ecos:changeme@database/ecos")
    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        main.check_configuration()
    monkeypatch.setenv("DATABASE_URL", "postgresql://ecos:Xk29dj3@database/ecos")
    main.check_configuration()


def test_chat_message_length_is_bounded():
    from pydantic import ValidationError

    from models import MAX_CHAT_MESSAGE_CHARS, ChatIn
    ChatIn(message="x" * MAX_CHAT_MESSAGE_CHARS)
    for bad in ("", "x" * (MAX_CHAT_MESSAGE_CHARS + 1)):
        with pytest.raises(ValidationError):
            ChatIn(message=bad)


# ==================== PIÈCES JOINTES ====================

@pytest.fixture
def files(session, monkeypatch):
    import storage as storage_module
    from models import Attachment, Attempts, ClinicalCase, StationType, User, UserRole

    stored = {"img/1/ecg.png": PNG}

    async def get_file(path):
        if path not in stored:
            raise FileNotFoundError(path)
        return stored[path]
    monkeypatch.setattr(storage_module.storage, "get_file", get_file)

    users = {name: User(username=name, hashed_password="x", role=role) for name, role in
             (("prof", UserRole.teacher), ("etu", UserRole.student), ("etu2", UserRole.student))}
    for u in users.values():
        session.add(u)
    session.commit()
    case = ClinicalCase(title="Palpitations", created_by=users["prof"].id, station_type=StationType.patient_interview,
                        student_instructions="-", scenario_context="-", patient_prompt="-", duration_seconds=600)
    session.add(case)
    session.commit()
    att = Attachment(case_id=case.id, filename='ecg"; x=.png', stored_filename="ecg.png", display_name="ECG",
                     kind="image", mime_type="image/png", size_bytes=len(PNG), file_path="img/1/ecg.png",
                     file_url="/x")
    attempt = Attempts(user_id=users["etu"].id, case_id=case.id, created_at=datetime.utcnow(),
                       expires_at=datetime.utcnow() + timedelta(minutes=10))
    session.add(att)
    session.add(attempt)
    session.commit()
    return {"users": users, "attachment": att, "attempt": attempt}


@pytest_asyncio.fixture
async def files_client(session, files):
    import httpx
    from fastapi import FastAPI

    import attachment_routes
    from auth import get_current_user
    from db import get_session

    app = FastAPI()
    app.include_router(attachment_routes.router)
    current = {"user": files["users"]["etu"]}
    app.dependency_overrides[get_session] = lambda: session
    app.dependency_overrides[get_current_user] = lambda: current["user"]
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        c.as_user = lambda name: current.__setitem__("user", files["users"][name])
        yield c


@pytest.mark.asyncio
async def test_students_only_get_documents_shown_to_them(files_client, files, session):
    from models import ChatRole, Message
    url = f"/attachments/download/{files['attachment'].id}"

    # Pas encore montré : invisible (pas de fuite des documents avant la station)
    assert (await files_client.get(url)).status_code == 404
    assert (await files_client.get(f"/attachments/case/{files['attachment'].case_id}")).status_code == 403
    assert (await files_client.get(f"/attachments/{files['attachment'].id}")).status_code == 403

    session.add(Message(attempt_id=files["attempt"].id, role=ChatRole.examiner, content="ECG",
                        attachment_id=files["attachment"].id))
    session.commit()
    r = await files_client.get(url)
    assert r.status_code == 200 and r.content == PNG
    assert r.headers["x-content-type-options"] == "nosniff"
    assert "sandbox" in r.headers["content-security-policy"]
    assert r.headers["content-type"] == "image/png"
    # Nom de fichier assaini : pas d'injection de paramètres dans l'en-tête
    assert 'filename="ecg__ x=.png"' in r.headers["content-disposition"]

    # Un autre étudiant ne l'a pas vu
    files_client.as_user("etu2")
    assert (await files_client.get(url)).status_code == 404
    files_client.as_user("prof")
    assert (await files_client.get(url)).status_code == 200


@pytest.mark.asyncio
async def test_download_requires_login(session, files):
    import httpx
    from fastapi import FastAPI

    import attachment_routes
    from db import get_session

    app = FastAPI()
    app.include_router(attachment_routes.router)
    app.dependency_overrides[get_session] = lambda: session
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        assert (await c.get(f"/attachments/download/{files['attachment'].id}")).status_code == 401


def test_upload_type_comes_from_content():
    from fastapi import HTTPException

    from attachment_routes import checked_upload, sniff_mime
    assert checked_upload(PNG) == ("image/png", "image", ".png")
    assert sniff_mime(b"%PDF-1.7 ...") == "application/pdf"
    for data in (b"<html><script>alert(1)</script>", b"MZ\x90\x00", b""):
        with pytest.raises(HTTPException) as exc:
            checked_upload(data)
        assert exc.value.status_code == 415
    with pytest.raises(HTTPException) as exc:
        checked_upload(PNG, allowed={"application/pdf"})
    assert exc.value.status_code == 415
