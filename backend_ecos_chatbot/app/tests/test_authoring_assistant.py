"""Assistant de rédaction : contexte envoyé au LLM et filtrage des propositions."""
import json
from pathlib import Path

import pytest

import authoring_assistant
from authoring_assistant import AssistantError, AssistantInputError, assist
from case_examples import dupont_sheet
from conftest import FakeAsyncClient, completion
from corpus import parse_sfc_chapter, store_chapter

FIXTURE = Path(__file__).parent / "fixtures" / "sfc_chapter_fictif.html"


@pytest.fixture
def stored(session):
    """Corpus fictif (item 999) en base ; renvoie les identifiants des extraits."""
    from sqlmodel import select

    from models import CorpusChunk

    store_chapter(session, parse_sfc_chapter(FIXTURE.read_text(encoding="utf-8"), "https://example.org/ch99/"))
    session.commit()
    return {c.text: c.id for c in session.exec(select(CorpusChunk)).all()}


def _sheet(**drop):
    sheet = dupont_sheet()
    sheet.station.edn_items = [999]
    sheet.facts = [f for f in sheet.facts if f.category not in drop.get("categories", ())]
    return sheet


def _reply(payload):
    return completion(content=json.dumps(payload, ensure_ascii=False))


@pytest.mark.asyncio
async def test_interview_facts_are_filtered_and_sourced(session, stored):
    sheet = _sheet(categories=("allergie", "mode_de_vie"))
    chunk_id = next(i for text, i in stored.items() if "tabagisme fictif" in text)
    client = FakeAsyncClient([_reply({"facts": [
        {"category": "mode_de_vie", "label": "Tabagisme actif 30 PA", "patient_words": "Je fume un paquet par jour depuis trente ans.",
         "disclosure": "sur_question", "asked_about": "le tabac", "source_ids": [chunk_id, 999999]},
        {"category": "histoire", "label": "Évoque lui-même un infarctus", "patient_words": "J'ai peur que ce soit un infarctus.",
         "disclosure": "spontane", "asked_about": "ses craintes", "source_ids": []},
        {"category": "antecedent", "label": "HTA", "patient_words": "J'ai de la tension.",
         "disclosure": "sur_question", "asked_about": "les antécédents médicaux", "source_ids": []},
        {"category": "allergie", "label": "Pas d'allergie connue", "patient_words": "Pas d'allergie, pas de dyspnée.",
         "disclosure": "sur_question", "asked_about": "les allergies", "source_ids": []},
    ]})])

    proposal = await assist(sheet, "interrogatoire", session=session, client=client, model="Qwen/Qwen3-8B")

    request = client.requests[0]
    assert request["response_format"]["type"] == "json_schema"
    assert request["extra_body"] == {"chat_template_kwargs": {"enable_thinking": False}}
    user = request["messages"][1]["content"]
    assert f"[{chunk_id}] Item 999 – Maladie fictive de Test" in user          # extraits numérotés
    assert "Allergies" in user and "Mode de vie" in user                       # catégories manquantes
    assert "[f_motif]" in user                                                 # faits existants

    labels = [f.label for f in proposal.facts]
    assert labels == ["Tabagisme actif 30 PA", "Pas d'allergie connue"]
    assert all(f.generated for f in proposal.facts)
    assert [s.chunk_id for s in proposal.facts[0].sources] == [chunk_id]     # source inventée retirée
    notes = " ".join(proposal.notes)
    assert "infarctus" in notes and "déjà dans la fiche" in notes and "dyspnee" in notes
    assert proposal.sources and all(s.url == "https://example.org/ch99/" for s in proposal.sources)


@pytest.mark.asyncio
async def test_language_rewrites_only_flagged_facts(session):
    sheet = _sheet()
    sheet.facts[1].patient_words = "Douleur rétrosternale"
    target = sheet.facts[1].id
    client = FakeAsyncClient([_reply({"rewrites": [
        {"fact_id": target, "patient_words": "J'ai mal juste là, au milieu de la poitrine."},
        {"fact_id": "f_inconnu", "patient_words": "..."},
    ]})])
    proposal = await assist(sheet, "langage", session=session, client=client)
    assert [(r.fact_id, r.before) for r in proposal.rewrites] == [(target, "Douleur rétrosternale")]
    assert f"[{target}]" in client.requests[0]["messages"][1]["content"]

    # Rien à reformuler : pas d'appel au LLM
    proposal = await assist(dupont_sheet(), "langage", session=session, client=FakeAsyncClient([]))
    assert proposal.rewrites == [] and proposal.notes


@pytest.mark.asyncio
async def test_grid_links_only_existing_facts(session, stored):
    sheet = _sheet()
    sheet.correction.grid = []
    client = FakeAsyncClient([_reply({"grid": [
        {"criterion": "Recherche le tabagisme", "points": 1, "description": "Demande la consommation de tabac",
         "fact_ids": ["f_tabac", "f_fantome"], "source_ids": []},
        {"criterion": "Se présente", "points": -2, "description": "Nom et fonction", "fact_ids": [], "source_ids": []},
    ]})])
    proposal = await assist(sheet, "grille", session=session, client=client)
    user = client.requests[0]["messages"][1]["content"]
    assert "Connaître la définition de la maladie fictive" in user        # objectifs de rang A ajoutés
    assert [g.fact_ids for g in proposal.grid] == [["f_tabac"], []]
    assert proposal.grid[1].points == 0.5
    assert "f_fantome" in " ".join(proposal.notes)

    with pytest.raises(AssistantInputError):
        await assist(_sheet(categories=tuple(c for c in authoring_assistant.CATEGORY_LABELS)), "grille",
                     session=session, client=FakeAsyncClient([]))


@pytest.mark.asyncio
async def test_persona_and_exam(session):
    sheet = _sheet()
    client = FakeAsyncClient([
        _reply({"personality": "Réservé", "emotional_state": "Inquiet", "concerns": ["son travail"],
                "spontaneous_questions": ["C'est grave ?"], "reactions": [{"when": "si on le rassure", "then": "il se détend"}]}),
        _reply({"exam_findings": [{"id": "constantes", "label": "Constantes", "findings": "déjà là"},
                                  {"id": "abdomen", "label": "Abdomen", "findings": "Souple, indolore"}]}),
    ])
    persona = await assist(sheet, "personnage", session=session, client=client)
    assert persona.persona.reactions[0].generated and persona.persona.spontaneous_questions == ["C'est grave ?"]
    exam = await assist(sheet, "examen", session=session, client=client)
    assert [e.id for e in exam.exam_findings] == ["abdomen"]                 # constantes déjà saisies


@pytest.mark.asyncio
async def test_unreadable_answer(session):
    with pytest.raises(AssistantError):
        await assist(_sheet(), "examen", session=session, client=FakeAsyncClient([completion(content="pas du json")]))


@pytest.mark.asyncio
async def test_assist_route(session, monkeypatch):
    import httpx
    from fastapi import FastAPI

    import authoring_routes
    from auth import get_current_user
    from db import get_session
    from models import ClinicalCase, User, UserRole

    prof = User(username="prof", hashed_password="x", role=UserRole.teacher)
    session.add(prof)
    session.commit()
    case = ClinicalCase(title="Brouillon", created_by=prof.id, student_instructions="", scenario_context="",
                        duration_seconds=480, sheet=_sheet().model_dump(mode="json"))
    session.add(case)
    session.commit()

    fake = FakeAsyncClient([_reply({"exam_findings": [{"id": "abdomen", "label": "Abdomen", "findings": "Souple"}]})])
    monkeypatch.setattr(authoring_assistant, "_client", lambda base_url, api_key: fake)
    app = FastAPI()
    app.include_router(authoring_routes.router, prefix="/authoring")
    app.dependency_overrides[get_session] = lambda: session
    app.dependency_overrides[get_current_user] = lambda: prof
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        r = await client.post(f"/authoring/cases/{case.id}/assist", json={"task": "examen"})
        assert r.status_code == 200, r.text
        assert r.json()["exam_findings"][0]["generated"] is True
        # La fiche envoyée par l'éditeur (non enregistrée) est prioritaire
        empty = _sheet()
        empty.facts = []
        r = await client.post(f"/authoring/cases/{case.id}/assist",
                              json={"task": "grille", "sheet": empty.model_dump(mode="json")})
        assert r.status_code == 422
        r = await client.post(f"/authoring/cases/{case.id}/assist", json={"task": "examen"})
        assert r.status_code == 502                                            # plus de réponse : erreur LLM
