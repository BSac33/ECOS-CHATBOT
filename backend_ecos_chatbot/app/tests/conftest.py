"""Configuration commune des tests : pas de PostgreSQL ni de LLM requis."""
import os
import sys
from pathlib import Path
from types import SimpleNamespace

# Variables lues à l'import des modules de l'app
os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("GEMINI_API_KEY", "test-key")
os.environ.setdefault("SECRET_KEY", "test-secret")

# Les modules de l'app s'importent à plat (from models import ...)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


# ---------- Base de test et cas clinique (partagés par les tests de routes) ----------

import pytest  # noqa: E402
from contextlib import contextmanager  # noqa: E402
from datetime import datetime, timedelta  # noqa: E402


@pytest.fixture
def session():
    """SQLite en mémoire par défaut ; TEST_DATABASE_URL=postgresql://... pour tester
    sur une base PostgreSQL migrée (chaque test est annulé par rollback)."""
    from sqlalchemy.pool import StaticPool
    from sqlmodel import Session, SQLModel, create_engine

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
    import chat_routes
    from models import Attachment, Attempts, ClinicalCase, StationType, User

    monkeypatch.setenv("LLM_PROVIDER", "vllm")
    monkeypatch.delenv("PATIENT_AGENT_ENABLED", raising=False)

    # Le flux SSE écrit avec sa propre session : on la redirige vers la base de test
    @contextmanager
    def test_write_session():
        yield session
    monkeypatch.setattr(chat_routes, "_write_session", test_write_session)

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


# ---------- Faux client OpenAI-compatible ----------

def tool_call(name: str, arguments: str, call_id: str = "call_1"):
    return SimpleNamespace(id=call_id, type="function", function=SimpleNamespace(name=name, arguments=arguments))


def completion(content=None, tool_calls=None):
    message = SimpleNamespace(content=content, tool_calls=tool_calls)
    return SimpleNamespace(choices=[SimpleNamespace(message=message)])


def _chunk(content=None, tool_calls=None, finish_reason=None):
    delta = SimpleNamespace(content=content, tool_calls=tool_calls)
    return SimpleNamespace(choices=[SimpleNamespace(delta=delta, finish_reason=finish_reason)])


async def as_stream(response, chunk_size=4):
    """Convertit une réponse complète en flux de morceaux, comme vLLM en mode stream.

    Le texte est découpé en morceaux de `chunk_size` caractères (les balises se
    retrouvent coupées) ; les arguments d'outils arrivent en deux morceaux.
    """
    message = response.choices[0].message
    content = message.content or ""
    for i in range(0, len(content), chunk_size):
        yield _chunk(content=content[i:i + chunk_size])
    for idx, tc in enumerate(message.tool_calls or []):
        args = tc.function.arguments
        half = len(args) // 2
        yield _chunk(tool_calls=[SimpleNamespace(
            index=idx, id=tc.id, type="function",
            function=SimpleNamespace(name=tc.function.name, arguments=args[:half]))])
        yield _chunk(tool_calls=[SimpleNamespace(
            index=idx, id=None, type=None,
            function=SimpleNamespace(name=None, arguments=args[half:]))])
    yield _chunk(finish_reason="tool_calls" if message.tool_calls else "stop")


class FakeAsyncClient:
    """Rejoue une liste de réponses et enregistre les requêtes reçues."""

    def __init__(self, responses, chunk_size=4):
        self._responses = list(responses)
        self._chunk_size = chunk_size
        self.requests = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    async def _create(self, **kwargs):
        # Copie défensive : la liste messages est mutée par l'agent ensuite
        kwargs = {**kwargs, "messages": [dict(m) for m in kwargs["messages"]]}
        self.requests.append(kwargs)
        if not self._responses:
            raise AssertionError("Plus de réponse scriptée disponible")
        response = self._responses.pop(0)
        if kwargs.get("stream"):
            return as_stream(response, self._chunk_size)
        return response
