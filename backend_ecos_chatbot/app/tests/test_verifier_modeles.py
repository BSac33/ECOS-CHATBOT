"""Script de vérification d'un serveur de modèles (scripts/verifier_modeles.py), avec de faux serveurs."""
import asyncio
import json
from types import SimpleNamespace

from openai import BadRequestError

from scripts import verifier_modeles as vm
from tests.conftest import FakeAsyncClient, complete_evaluation, completion, tool_call

CFG = vm.Config(base_url="http://h100/v1", model="qwen-27b", api_key="k", arbiter_base_url="http://h100/v1",
                arbiter_model="qwen-27b", arbiter_api_key="k", arbiter_timeout=2.0)


class Models:
    def __init__(self, ids):
        self.ids = ids

    async def list(self):
        return SimpleNamespace(data=[SimpleNamespace(id=i) for i in self.ids])


class SyncClient:
    """Correction : renvoie une grille complète."""

    def __init__(self):
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        grid = vm.Station().grid()
        return completion(json.dumps(complete_evaluation(grid)["evaluation"]))


def arbiter(category):
    return completion(json.dumps({"category": category, "tone": "NEUTRAL"}))


def server(responses, ids=("qwen-27b",)):
    client = FakeAsyncClient(responses)
    client.models = Models(list(ids))
    return client


def healthy_responses():
    zone = vm.Station().rt["exam_findings"][0]["id"]
    return [
        completion(tool_calls=[tool_call("noter_examen", '{"zone": "tension"}')]),       # outils activés
        completion("Bonjour docteur. J'ai mal à la poitrine depuis ce matin."),             # 1re réplique
        completion(tool_calls=[tool_call("resultat_examen_clinique", json.dumps({"zones": [zone]}))]),
        completion("D'accord, allez-y."),                                                   # après l'outil
        arbiter("CLINICAL_QUESTION"),
        arbiter("META_EXFILTRATION"),
    ]


def test_healthy_server_is_ready(capsys):
    client = server(healthy_responses() + [completion("Bonjour docteur.")] * 3)
    checks = asyncio.run(vm.run_checks(CFG, charge=3, client=client, sync_client=SyncClient()))
    statuses = {c.name: c.status for c in checks}
    assert all(s == "OK" for s in statuses.values()), checks
    assert "Charge : 3 répliques simultanées" in statuses and "Charge : 3 corrections simultanées" in statuses
    text = vm.report(CFG, checks)
    assert text.endswith("Verdict : prêt")
    # Toutes les requêtes du patient passent par l'agent de production (outils déclarés, flux)
    patient = [r for r in client.requests if r.get("stream")]
    assert patient and all(r["model"] == "qwen-27b" and r["tools"] for r in patient)


def test_wrong_model_name_stops_early():
    checks = asyncio.run(vm.run_checks(CFG, client=server([], ids=["chu-extraction"]), sync_client=SyncClient()))
    assert len(checks) == 1 and checks[0].blocking
    assert "chu-extraction" in checks[0].detail and "VLLM_MODEL" in checks[0].hint


def test_tool_calling_disabled_is_explained():
    request = SimpleNamespace(method="POST", url="http://h100/v1/chat/completions", headers={}, extensions={})
    response = SimpleNamespace(status_code=400, headers={}, request=request)
    refused = BadRequestError('"auto" tool choice requires --enable-auto-tool-choice', response=response, body=None)

    class Refusing(FakeAsyncClient):
        async def _create(self, **kwargs):
            if kwargs.get("tools"):
                raise refused
            return await super()._create(**kwargs)

    client = Refusing([arbiter("CLINICAL_QUESTION"), arbiter("META_EXFILTRATION")])
    client.models = Models(["qwen-27b"])
    checks = asyncio.run(vm.run_checks(CFG, client=client, sync_client=SyncClient()))
    tools = next(c for c in checks if c.name == "Appel d'outils activé")
    assert tools.blocking and "--enable-auto-tool-choice" in tools.hint
    assert "PATIENT_AGENT_ENABLED=false" in tools.hint
    assert "à corriger" in vm.report(CFG, checks)


def test_config_defaults_to_one_server_for_everything(monkeypatch):
    for name in ("VLLM_ARBITER_BASE_URL", "VLLM_ARBITER_MODEL", "VLLM_ARBITER_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("VLLM_BASE_URL", "http://h100/v1")
    monkeypatch.setenv("VLLM_MODEL", "qwen-27b")
    monkeypatch.setenv("VLLM_API_KEY", "k")
    args = vm.argparse.Namespace(base_url=None, model=None, api_key=None, arbitre_base_url=None,
                                 arbitre_model=None, arbitre_api_key=None)
    cfg = vm.config_from(args)
    assert (cfg.arbiter_base_url, cfg.arbiter_model, cfg.arbiter_api_key) == ("http://h100/v1", "qwen-27b", "k")
