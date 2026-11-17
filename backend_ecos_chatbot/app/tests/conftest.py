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


# ---------- Faux client OpenAI-compatible ----------

def tool_call(name: str, arguments: str, call_id: str = "call_1"):
    return SimpleNamespace(id=call_id, type="function", function=SimpleNamespace(name=name, arguments=arguments))


def completion(content=None, tool_calls=None):
    message = SimpleNamespace(content=content, tool_calls=tool_calls)
    return SimpleNamespace(choices=[SimpleNamespace(message=message)])


class FakeAsyncClient:
    """Rejoue une liste de réponses et enregistre les requêtes reçues."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.requests = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    async def _create(self, **kwargs):
        # Copie défensive : la liste messages est mutée par l'agent ensuite
        kwargs = {**kwargs, "messages": [dict(m) for m in kwargs["messages"]]}
        self.requests.append(kwargs)
        if not self._responses:
            raise AssertionError("Plus de réponse scriptée disponible")
        return self._responses.pop(0)
