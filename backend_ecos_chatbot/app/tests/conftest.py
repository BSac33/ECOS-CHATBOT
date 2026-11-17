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
