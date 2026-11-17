"""Tests de l'agent patient (outils + boucle), avec un faux client LLM."""
import json
from types import SimpleNamespace

import pytest

from conftest import FakeAsyncClient, completion, tool_call
from patient_agent import (
    FALLBACK_REPLY,
    _TagFilter,
    CaseToolContext,
    build_agent_system_instruction,
    build_tools,
    clean_reply,
    execute_tool,
    run_patient_agent,
    stream_patient_agent,
)

FINDINGS = [
    {"id": "constantes", "label": "Constantes vitales", "findings": "PA 158/94 mmHg, FC 102/min"},
    {"id": "auscultation_cardiaque", "label": "Auscultation cardiaque", "findings": "Pas de souffle"},
]


def make_case(attachments=None, exam_findings=None):
    return SimpleNamespace(attachments=attachments or [], exam_findings=exam_findings)


def make_attachment(att_id="11111111-1111-1111-1111-111111111111", name="ECG 18 dérivations",
                    keywords="ecg,électrocardiogramme", available=True):
    return SimpleNamespace(
        id=att_id, display_name=name, trigger_keywords=keywords,
        mime_type="image/png", is_available_during_case=available,
        description="Sus-décalage ST en inférieur",  # ne doit JAMAIS être exposé au patient
    )


@pytest.fixture
def ctx():
    return CaseToolContext.from_case(make_case([make_attachment()], FINDINGS))


async def run(ctx, responses, **kwargs):
    client = FakeAsyncClient(responses)
    result = await run_patient_agent(
        patient_prompt="Tu es Mr. Dupont, 58 ans.",
        history=[{"role": "student", "content": "Bonjour"}, {"role": "patient", "content": "Bonjour docteur."}],
        student_message=kwargs.pop("student_message", "Je vais vous faire un ECG."),
        ctx=ctx,
        client=client,
        model=kwargs.pop("model", "Qwen/Qwen3-8B"),
        **kwargs,
    )
    return result, client


# ---------- Contexte et définitions d'outils ----------

def test_context_skips_unavailable_documents_and_invalid_findings():
    case = make_case(
        [make_attachment(), make_attachment(att_id="2", name="Scanner", available=False)],
        FINDINGS + [{"id": "vide"}, "pas un dict"],
    )
    ctx = CaseToolContext.from_case(case)
    assert [d.display_name for d in ctx.documents] == ["ECG 18 dérivations"]
    assert [d.key for d in ctx.documents] == ["doc_1"]
    assert [f["id"] for f in ctx.exam_findings] == ["constantes", "auscultation_cardiaque"]


def test_tools_depend_on_case_content(ctx):
    names = [t["function"]["name"] for t in build_tools(ctx)]
    assert names == ["afficher_document", "resultat_examen_clinique", "signaler_hors_cadre"]

    bare = CaseToolContext.from_case(make_case())
    assert [t["function"]["name"] for t in build_tools(bare)] == ["signaler_hors_cadre"]


def test_tools_never_expose_uuid_nor_document_description(ctx):
    dumped = json.dumps(build_tools(ctx), ensure_ascii=False)
    assert "11111111" not in dumped
    assert "Sus-décalage" not in dumped
    assert "doc_1" in dumped and "ecg,électrocardiogramme" in dumped


def test_system_instruction_mentions_only_available_tools_and_state():
    bare = CaseToolContext.from_case(make_case())
    prompt = build_agent_system_instruction("PROMPT", bare, ["Document affiché – ECG"])
    assert "afficher_document" not in prompt
    assert "resultat_examen_clinique" not in prompt
    assert "signaler_hors_cadre" in prompt
    assert "Document affiché – ECG" in prompt


def test_oral_rules_only_in_voice_mode(ctx):
    assert "RÉPONSE ORALE" not in build_agent_system_instruction("P", ctx)
    oral = build_agent_system_instruction("P", ctx, oral=True)
    assert "RÉPONSE ORALE" in oral and "toutes lettres" in oral


# ---------- Exécution pure des outils ----------

def test_exam_findings_are_not_sent_back_to_the_patient_model(ctx):
    text, event = execute_tool("resultat_examen_clinique", '{"zones": ["constantes", "constantes", "inconnue"]}', ctx)
    assert event.type == "exam_findings"
    assert [f["id"] for f in event.payload["findings"]] == ["constantes"]
    assert "158/94" not in text  # le patient ne peut pas réciter ce qu'il ne voit pas
    assert "Constantes vitales" in text


@pytest.mark.parametrize("name,args", [
    ("afficher_document", '{"document": "doc_99"}'),
    ("afficher_document", "pas du json"),
    ("resultat_examen_clinique", '{"zones": ["inconnue"]}'),
    ("outil_fantome", "{}"),
])
def test_invalid_tool_calls_produce_no_event(ctx, name, args):
    text, event = execute_tool(name, args, ctx)
    assert event is None
    assert text.startswith("Erreur")


def test_flag_tool_normalises_unknown_values(ctx):
    _, event = execute_tool("signaler_hors_cadre", '{"categorie": "AUTRE", "gravite": "extreme", "motif": "insulte"}', ctx)
    assert event.payload == {"category": "HORS_SUJET", "severity": "moderee", "detail": "insulte"}


def test_clean_reply_strips_reasoning_and_raw_tool_tags():
    raw = "<think>je réfléchis</think>D'accord. <tool_call>{\"name\": \"x\"}</tool_call>"
    assert clean_reply(raw) == "D'accord."
    assert clean_reply("<think>non fermé") == ""
    assert clean_reply(None) == ""


# ---------- Boucle agent ----------

@pytest.mark.asyncio
async def test_plain_reply_without_tools(ctx):
    result, client = await run(ctx, [completion("J'ai très mal, docteur.")], student_message="Où avez-vous mal ?")
    assert result.reply == "J'ai très mal, docteur."
    assert result.events == []
    request = client.requests[0]
    assert request["tool_choice"] == "auto"
    assert request["extra_body"] == {"chat_template_kwargs": {"enable_thinking": False}}
    roles = [m["role"] for m in request["messages"]]
    assert roles == ["system", "user", "assistant", "user"]


@pytest.mark.asyncio
async def test_document_tool_round_trip(ctx):
    result, client = await run(ctx, [
        completion(None, [tool_call("afficher_document", '{"document": "doc_1"}')]),
        completion("D'accord, allez-y."),
    ])
    assert result.reply == "D'accord, allez-y."
    assert [d.attachment_id for d in result.documents] == ["11111111-1111-1111-1111-111111111111"]
    second = client.requests[1]["messages"]
    assert second[-2]["role"] == "assistant" and second[-2]["tool_calls"][0]["function"]["name"] == "afficher_document"
    assert second[-1]["role"] == "tool" and second[-1]["tool_call_id"] == "call_1"


@pytest.mark.asyncio
async def test_same_document_is_shown_once_per_turn(ctx):
    result, _ = await run(ctx, [
        completion(None, [
            tool_call("afficher_document", '{"document": "doc_1"}', "a"),
            tool_call("afficher_document", '{"document": "doc_1"}', "b"),
        ]),
        completion("Voilà."),
    ])
    assert len(result.documents) == 1


@pytest.mark.asyncio
async def test_flag_then_in_character_reply(ctx):
    result, _ = await run(ctx, [
        completion(None, [tool_call("signaler_hors_cadre", '{"categorie": "IRRESPECT", "gravite": "grave"}')]),
        completion("C'est blessant… Je vous demande de me parler avec respect."),
    ], student_message="T'es lourd papy")
    assert result.flags == [{"category": "IRRESPECT", "severity": "grave", "detail": None}]
    assert result.reply.startswith("C'est blessant")


@pytest.mark.asyncio
async def test_tool_loop_is_bounded_and_falls_back(ctx):
    looping = completion(None, [tool_call("signaler_hors_cadre", '{"categorie": "HORS_SUJET", "gravite": "faible"}')])
    result, client = await run(ctx, [looping, looping, completion("")])
    assert len(client.requests) == 3
    assert [r["tool_choice"] for r in client.requests] == ["auto", "auto", "none"]
    assert result.reply == FALLBACK_REPLY


@pytest.mark.asyncio
async def test_no_thinking_kwargs_for_non_qwen3_models(ctx):
    _, client = await run(ctx, [completion("Oui.")], model="Qwen/Qwen2.5-7B-Instruct")
    assert "extra_body" not in client.requests[0]


# ---------- Flux ----------

@pytest.mark.parametrize("pieces,expected", [
    (["<thi", "nk>je réfléchis</th", "ink>Bon", "jour."], "Bonjour."),
    (["Oui <tool", "_call>{\"name\": \"x\"}</tool_", "call>docteur."], "Oui docteur."),
    (["La douleur est < 5 ", "sur 10."], "La douleur est < 5 sur 10."),
    (["J'ai mal <"], "J'ai mal <"),
])
def test_tag_filter_across_chunk_boundaries(pieces, expected):
    f = _TagFilter()
    out = "".join(f.feed(p) for p in pieces) + f.flush()
    assert out == expected


@pytest.mark.asyncio
async def test_stream_yields_small_deltas_then_done(ctx):
    client = FakeAsyncClient([completion("<think></think>J'ai très mal, docteur.")], chunk_size=3)
    items = [i async for i in stream_patient_agent(
        patient_prompt="P", history=[], student_message="Où ?", ctx=ctx, client=client, model="Qwen/Qwen3-8B")]
    deltas = [v for k, v in items if k == "delta"]
    assert len(deltas) > 3
    assert "".join(deltas) == "J'ai très mal, docteur."
    assert items[-1][0] == "done" and items[-1][1].reply == "J'ai très mal, docteur."


@pytest.mark.asyncio
async def test_text_before_and_after_tool_forms_one_reply(ctx):
    client = FakeAsyncClient([
        completion("D'accord.", [tool_call("afficher_document", '{"document": "doc_1"}')]),
        completion("C'est grave ?"),
    ])
    items = [i async for i in stream_patient_agent(
        patient_prompt="P", history=[], student_message="ECG", ctx=ctx, client=client, model="m")]
    kinds = [k for k, _ in items]
    # le texte du 1er tour, puis l'outil, puis le texte du 2e tour
    assert kinds.index("event") > kinds.index("delta")
    assert "".join(v for k, v in items if k == "delta") == "D'accord. C'est grave ?"
    assert items[-1][1].reply == "D'accord. C'est grave ?"
    # l'historique renvoyé au modèle contient le texte déjà prononcé
    assert client.requests[1]["messages"][-2]["content"] == "D'accord."


# ---------- Bout en bout avec le vrai SDK OpenAI (serveur vLLM simulé, SSE) ----------

def _sse_body(deltas, finish_reason):
    """Corps SSE au format de vLLM : un événement data par morceau, puis [DONE]."""
    lines = []
    for i, delta in enumerate(deltas + [{}]):
        chunk = {
            "id": "chatcmpl-1", "object": "chat.completion.chunk", "created": 0, "model": "Qwen/Qwen3-8B",
            "choices": [{"index": 0, "delta": delta,
                         "finish_reason": finish_reason if i == len(deltas) else None}],
        }
        lines.append("data: " + json.dumps(chunk, ensure_ascii=False) + "\n\n")
    lines.append("data: [DONE]\n\n")
    return "".join(lines).encode()


@pytest.mark.asyncio
async def test_real_openai_sdk_wire_format(ctx):
    """Sérialisation réelle (stream, tools, tool_calls en morceaux, role=tool) via HTTP."""
    import httpx
    from openai import AsyncOpenAI

    bodies = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        bodies.append(body)
        if len(bodies) == 1:
            deltas = [
                {"role": "assistant", "content": ""},
                {"tool_calls": [{"index": 0, "id": "chatcmpl-tool-1", "type": "function",
                                 "function": {"name": "resultat_examen_clinique", "arguments": ""}}]},
                {"tool_calls": [{"index": 0, "function": {"arguments": "{\"zones\": [\"const"}}]},
                {"tool_calls": [{"index": 0, "function": {"arguments": "antes\"]}"}}]},
            ]
            content = _sse_body(deltas, "tool_calls")
        else:
            deltas = [{"role": "assistant", "content": ""}, {"content": "D'accord,"}, {"content": " allez-y."}]
            content = _sse_body(deltas, "stop")
        return httpx.Response(200, content=content, headers={"content-type": "text/event-stream"})

    client = AsyncOpenAI(base_url="http://vllm.test/v1", api_key="x",
                         http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    items = [item async for item in stream_patient_agent(
        patient_prompt="Tu es Mr. Dupont.", history=[], student_message="Je prends votre tension.",
        ctx=ctx, client=client, model="Qwen/Qwen3-8B",
    )]

    kinds = [k for k, _ in items]
    assert kinds == ["event", "delta", "delta", "done"]
    result = items[-1][1]
    assert result.reply == "D'accord, allez-y."
    assert [f["id"] for f in result.findings] == ["constantes"]

    first, second = bodies
    assert first["stream"] is True
    assert first["tool_choice"] == "auto"
    assert first["chat_template_kwargs"] == {"enable_thinking": False}  # extra_body fusionné au corps
    assert {t["function"]["name"] for t in first["tools"]} == {
        "afficher_document", "resultat_examen_clinique", "signaler_hors_cadre"}
    call = second["messages"][-2]["tool_calls"][0]
    assert call["id"] == "chatcmpl-tool-1"
    assert call["function"]["arguments"] == '{"zones": ["constantes"]}'  # morceaux recollés
    assert second["messages"][-1]["role"] == "tool"
    assert second["messages"][-1]["tool_call_id"] == "chatcmpl-tool-1"
    assert "158/94" not in json.dumps(second, ensure_ascii=False)
