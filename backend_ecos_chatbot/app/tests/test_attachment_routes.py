"""Routes /attachments : dépôt et suppression réservés à l'auteur du cas (ou admin),
lecture réservée aux utilisateurs connectés."""
import pytest
import pytest_asyncio
from sqlmodel import select

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16


@pytest.fixture
def people(session):
    from models import User, UserRole

    users = {
        "prof": User(username="prof", hashed_password="x", role=UserRole.teacher),
        "autre_prof": User(username="autre", hashed_password="x", role=UserRole.teacher),
        "admin": User(username="admin", hashed_password="x", role=UserRole.admin),
        "etu": User(username="etu", hashed_password="x", role=UserRole.student),
    }
    for u in users.values():
        session.add(u)
    session.commit()
    return users


@pytest.fixture
def case(session, people):
    from models import ClinicalCase

    c = ClinicalCase(title="Douleur thoracique", created_by=people["prof"].id,
                     student_instructions="Interrogez le patient", scenario_context="SCA",
                     duration_seconds=600)
    session.add(c)
    session.commit()
    return c


@pytest.fixture
def store(tmp_path, monkeypatch):
    import attachment_routes
    from storage import LocalStorage

    s = LocalStorage(str(tmp_path / "storage"))
    monkeypatch.setattr(attachment_routes, "storage", s)
    return s


@pytest_asyncio.fixture
async def client(session, people, store):
    """Client HTTP ; `client.as_user("prof")` change l'utilisateur connecté,
    `client.as_user(None)` retire la surcharge : la vraie authentification s'applique."""
    import httpx
    from fastapi import FastAPI

    import attachment_routes
    from auth import get_current_user
    from db import get_session

    app = FastAPI()
    app.include_router(attachment_routes.router)
    app.dependency_overrides[get_session] = lambda: session

    def as_user(name):
        if name is None:
            app.dependency_overrides.pop(get_current_user, None)
        else:
            user = people[name]
            app.dependency_overrides[get_current_user] = lambda: user

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        c.as_user = as_user
        as_user("prof")
        yield c


def _upload(client, case_id, name="ecg.png", available=True):
    return client.post(
        "/attachments/upload",
        files={"file": (name, PNG, "image/png")},
        data={"case_id": str(case_id), "display_name": "ECG",
              "is_available_during_case": str(available).lower()},
    )


def _attachments(session):
    from models import Attachment

    session.expire_all()
    return session.exec(select(Attachment)).all()


# ---------- Dépôt ----------

@pytest.mark.asyncio
async def test_upload_refused_without_authentication(client, session, case):
    client.as_user(None)
    r = await _upload(client, case.id)
    assert r.status_code == 401
    assert _attachments(session) == []


@pytest.mark.asyncio
async def test_upload_refused_for_student(client, session, case):
    client.as_user("etu")
    r = await _upload(client, case.id)
    assert r.status_code == 403
    assert _attachments(session) == []


@pytest.mark.asyncio
async def test_upload_refused_for_other_teacher(client, session, case, store):
    client.as_user("autre_prof")
    r = await _upload(client, case.id)
    assert r.status_code == 403
    assert _attachments(session) == []
    # Rien n'a été écrit sur le disque
    assert [p for p in store.base_path.rglob("*") if p.is_file()] == []


@pytest.mark.asyncio
async def test_upload_accepted_for_author_and_admin(client, session, case, store):
    r = await _upload(client, case.id)
    assert r.status_code == 200, r.text
    att = _attachments(session)[0]
    assert str(att.id) == r.json()["id"] and att.case_id == case.id
    assert (store.base_path / att.file_path).read_bytes() == PNG

    client.as_user("admin")
    assert (await _upload(client, case.id)).status_code == 200
    assert len(_attachments(session)) == 2


@pytest.mark.asyncio
async def test_upload_unknown_case(client):
    assert (await _upload(client, 9999)).status_code == 404


# ---------- Suppression ----------

@pytest.mark.asyncio
async def test_delete_restricted_to_author_or_admin(client, session, case, store):
    first = (await _upload(client, case.id)).json()["id"]
    second = (await _upload(client, case.id)).json()["id"]

    client.as_user(None)
    assert (await client.delete(f"/attachments/{first}")).status_code == 401
    client.as_user("etu")
    assert (await client.delete(f"/attachments/{first}")).status_code == 403
    client.as_user("autre_prof")
    assert (await client.delete(f"/attachments/{first}")).status_code == 403
    assert len(_attachments(session)) == 2

    client.as_user("prof")
    path = next(a.file_path for a in _attachments(session) if str(a.id) == first)
    assert (await client.delete(f"/attachments/{first}")).status_code == 200
    assert [str(a.id) for a in _attachments(session)] == [second]
    assert not (store.base_path / path).exists()

    client.as_user("admin")
    assert (await client.delete(f"/attachments/{second}")).status_code == 200
    assert _attachments(session) == []


# ---------- Lecture ----------

@pytest.mark.asyncio
async def test_read_routes_require_authentication(client, case):
    att_id = (await _upload(client, case.id)).json()["id"]
    routes = [f"/attachments/{att_id}", f"/attachments/case/{case.id}", f"/attachments/download/{att_id}"]

    client.as_user(None)
    for url in routes:
        assert (await client.get(url)).status_code == 401, url

    client.as_user("etu")
    for url in routes:
        assert (await client.get(url)).status_code == 200, url
    r = await client.get(f"/attachments/download/{att_id}")
    assert r.content == PNG and r.headers["content-type"] == "image/png"


@pytest.mark.asyncio
async def test_hidden_attachments_listed_only_for_author(client, case):
    visible = (await _upload(client, case.id)).json()["id"]
    hidden = (await _upload(client, case.id, available=False)).json()["id"]

    client.as_user("etu")
    r = await client.get(f"/attachments/case/{case.id}")
    assert [a["id"] for a in r.json()] == [visible]
    assert (await client.get(f"/attachments/case/{case.id}?available_only=false")).status_code == 403
    client.as_user("autre_prof")
    assert (await client.get(f"/attachments/case/{case.id}?available_only=false")).status_code == 403

    client.as_user("prof")
    r = await client.get(f"/attachments/case/{case.id}?available_only=false")
    assert r.status_code == 200 and {a["id"] for a in r.json()} == {visible, hidden}


@pytest.mark.asyncio
async def test_download_with_session_cookie(client, case):
    """Le chat et le débrief chargent les images via <img src> : seul le cookie est envoyé."""
    from auth import create_access_token

    att_id = (await _upload(client, case.id)).json()["id"]
    client.as_user(None)  # vraie chaîne get_token -> get_current_user

    client.cookies.set("access_token", create_access_token({"sub": "etu"}))
    r = await client.get(f"/attachments/download/{att_id}")
    assert r.status_code == 200 and r.content == PNG

    client.cookies.set("access_token", "jeton-invalide")
    assert (await client.get(f"/attachments/download/{att_id}")).status_code == 401
