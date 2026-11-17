"""Tests du mode vocal : WebSocket /chat/attempts/{id}/voice.

Vrai client WebSocket (TestClient Starlette) d'un côté, faux serveurs Kyutai
(vrai protocole WebSocket + msgpack) dans un thread de l'autre ; seuls le LLM
patient et l'arbitre sont simulés.
"""
import asyncio
import json
import threading

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import select
from starlette.websockets import WebSocketDisconnect

import chat_routes
import voice_routes
from arbiter import Verdict
from fake_kyutai import FakeKyutai, speech_frame
from kyutai_voice import pcm_to_bytes
from models import ChatRole, Message, ModerationEvent
from patient_agent import PatientAgentResult

ALLOW = Verdict("CLINICAL_QUESTION", "NEUTRAL", "llm")
BLOCK = Verdict("ABUSIVE", "INSULTING", "llm")
REPLY_CHUNKS = ["Ça a commen", "cé devant", " la télé", " ?"]
REPLY = "Ça a commencé devant la télé ?"


class KyutaiThread:
    """Faux serveurs Kyutai dans leur propre boucle asyncio (le TestClient a la sienne)."""

    def __init__(self, **kwargs):
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self.loop.run_forever, daemon=True)
        self.thread.start()
        self.server = asyncio.run_coroutine_threadsafe(FakeKyutai(**kwargs).start(), self.loop).result(5)

    def stop(self):
        asyncio.run_coroutine_threadsafe(self.server.stop(), self.loop).result(5)
        self.loop.call_soon_threadsafe(self.loop.stop)
        self.thread.join(5)


def fake_agent(chunks, reply):
    async def gen(**kwargs):
        for chunk in chunks:
            yield ("delta", chunk)
        yield ("done", PatientAgentResult(reply=reply))
    return gen


def arbiter_returning(verdict):
    async def arbiter(message, **kwargs):
        return verdict
    return arbiter


@pytest.fixture
def voice_app(world, monkeypatch):
    def setup(verdict=ALLOW, **kyutai_kwargs):
        if "segments" not in kyutai_kwargs:
            kyutai_kwargs.setdefault("words", ["Depuis", "quand", "avez-vous", "mal", "?"])
        kyutai = KyutaiThread(**kyutai_kwargs)
        cleanups.append(kyutai.stop)
        monkeypatch.setenv("KYUTAI_STT_URL", kyutai.server.url)
        monkeypatch.setenv("KYUTAI_TTS_URL", kyutai.server.url)
        monkeypatch.setenv("KYUTAI_TTS_DEFAULT_VOICE", "unmute-prod-website/fabieng-enhanced-v2.wav")
        monkeypatch.setattr(chat_routes, "stream_patient_agent", fake_agent(REPLY_CHUNKS, REPLY))
        monkeypatch.setattr(chat_routes, "arbitrate", arbiter_returning(verdict))

        async def authenticated(websocket):
            return world["user"]
        monkeypatch.setattr(voice_routes, "_authenticate", authenticated)

        app = FastAPI()
        app.include_router(voice_routes.router, prefix="/chat")
        return TestClient(app), kyutai.server

    cleanups = []
    yield setup
    for cleanup in cleanups:
        cleanup()


def url(world):
    return f"/chat/attempts/{world['attempt'].id}/voice"


def read_until(ws, stop_type, limit=500):
    """Lit les messages (JSON et audio binaire) jusqu'au type demandé."""
    events = []
    for _ in range(limit):
        message = ws.receive()
        if message.get("bytes") is not None:
            events.append(("audio", len(message["bytes"])))
            if stop_type == "audio":
                return events
            continue
        data = json.loads(message["text"])
        events.append((data["type"], data))
        if data["type"] == stop_type:
            return events
    raise AssertionError(f"{stop_type} jamais reçu : {[e[0] for e in events]}")


def speak(ws, frames=12):
    ws.send_json({"type": "start"})
    read_until(ws, "listening")
    for _ in range(frames):
        ws.send_bytes(pcm_to_bytes(speech_frame()))
    ws.send_json({"type": "stop"})


def test_push_to_talk_full_turn(voice_app, world, session):
    client, kyutai = voice_app()
    with client.websocket_connect(url(world)) as ws:
        ready = ws.receive_json()
        assert ready == {"type": "ready", "voice": "unmute-prod-website/fabieng-enhanced-v2.wav"}
        speak(ws)
        events = read_until(ws, "audio_end")

    kinds = [k for k, _ in events]
    # sous-titres en direct, transcription finale, texte du patient, voix
    assert "transcript_partial" in kinds
    final = next(d for k, d in events if k == "transcript_final")
    assert final["text"] == "Depuis quand avez-vous mal ?"
    assert "".join(d["text"] for k, d in events if k == "delta") == REPLY
    done = next(d for k, d in events if k == "done")
    assert done["patient_reply"] == REPLY and done["blocked"] is False
    audio = [n for k, n in events if k == "audio"]
    assert len(audio) == 6 and all(n == 1920 * 4 for n in audio)  # float32, 80 ms par trame
    assert kinds.index("transcript_final") < kinds.index("delta") < kinds.index("done") < kinds.index("audio_end")

    # La synthèse a reçu des mots entiers, ponctuation rattachée
    assert kyutai.tts_texts == ["Ça", "a", "commencé", "devant", "la", "télé?"]
    assert kyutai.tts_requests[0]["voice"] == "unmute-prod-website/fabieng-enhanced-v2.wav"

    # Persistance : tour vocal, même chemin que l'écrit
    rows = session.exec(select(Message).where(Message.attempt_id == world["attempt"].id)
                        .order_by(Message.created_at)).all()
    assert [(r.role, r.modality, r.content) for r in rows] == [
        (ChatRole.student, "voice", "Depuis quand avez-vous mal ?"),
        (ChatRole.patient, "voice", REPLY),
    ]


def test_voice_turn_asks_patient_for_oral_style(voice_app, world, monkeypatch):
    client, _ = voice_app()
    captured = {}

    async def agent(**kwargs):
        captured.update(kwargs)
        yield ("delta", "Oui.")
        yield ("done", PatientAgentResult(reply="Oui."))
    monkeypatch.setattr(chat_routes, "stream_patient_agent", agent)
    with client.websocket_connect(url(world)) as ws:
        ws.receive_json()
        speak(ws)
        read_until(ws, "done")
    assert captured["oral"] is True


def test_case_voice_is_used(voice_app, world, session):
    world["case"].voice_id = "cml-tts/fr/12977_10625_000037-0001.wav"
    session.add(world["case"])
    session.commit()
    client, _ = voice_app()
    with client.websocket_connect(url(world)) as ws:
        assert ws.receive_json()["voice"] == "cml-tts/fr/12977_10625_000037-0001.wav"


def test_barge_in_cuts_voice_but_keeps_the_exchange(voice_app, world, session):
    client, kyutai = voice_app(tts_frame_delay=0.3)  # voix lente : le patient parle encore
    with client.websocket_connect(url(world)) as ws:
        ws.receive_json()
        speak(ws)
        read_until(ws, "audio")  # le patient commence à parler
        ws.send_json({"type": "start"})  # l'étudiant lui coupe la parole
        cut = read_until(ws, "listening")
        # deuxième prise de parole
        for _ in range(12):
            ws.send_bytes(pcm_to_bytes(speech_frame()))
        ws.send_json({"type": "stop"})
        second = read_until(ws, "audio_end")

    assert "interrupted" in [k for k, _ in cut]
    # Plus aucune voix de la première réplique après la coupure
    before_second_turn = [k for k, _ in second[:[k for k, _ in second].index("transcript_final")]]
    assert "audio" not in before_second_turn
    # Couper la voix ne perd rien : les deux échanges sont enregistrés, dans l'ordre
    rows = session.exec(select(Message).where(Message.attempt_id == world["attempt"].id)
                        .order_by(Message.created_at)).all()
    assert [(r.role, r.content) for r in rows] == [
        (ChatRole.student, "Depuis quand avez-vous mal ?"), (ChatRole.patient, REPLY),
        (ChatRole.student, "Depuis quand avez-vous mal ?"), (ChatRole.patient, REPLY),
    ]


def test_blocked_message_gets_no_voice(voice_app, world, session):
    client, kyutai = voice_app(verdict=BLOCK)
    with client.websocket_connect(url(world)) as ws:
        ws.receive_json()
        speak(ws)
        events = read_until(ws, "done")
        assert events[-1][1]["blocked"] is True
        # Rien d'autre n'arrive ensuite (pas de voix) : on reprend directement la parole
        ws.send_json({"type": "start"})
        after = read_until(ws, "listening")
    assert [k for k, _ in after] == ["listening"]
    assert not [k for k, _ in events if k in ("audio", "delta")]
    assert kyutai.tts_texts == []
    assert session.exec(select(Message)).all() == []
    assert [e.action for e in session.exec(select(ModerationEvent)).all()] == ["blocked"]


def test_tts_unavailable_falls_back_to_text(voice_app, world, session):
    client, _ = voice_app(tts_error="at capacity")
    with client.websocket_connect(url(world)) as ws:
        ws.receive_json()
        speak(ws)
        events = read_until(ws, "done")
    kinds = [k for k, _ in events]
    assert "voice_unavailable" in kinds and "audio" not in kinds
    assert events[-1][1]["patient_reply"] == REPLY
    assert len(session.exec(select(Message)).all()) == 2  # la réplique écrite est enregistrée


def test_stt_unavailable(voice_app, world):
    client, _ = voice_app(stt_error="at capacity")
    with client.websocket_connect(url(world)) as ws:
        ws.receive_json()
        speak(ws)
        events = read_until(ws, "error")
    assert events[-1][1]["status"] == 503


def test_silence_produces_no_turn(voice_app, world, session):
    client, _ = voice_app()
    with client.websocket_connect(url(world)) as ws:
        ws.receive_json()
        ws.send_json({"type": "start"})
        read_until(ws, "listening")
        for _ in range(5):
            ws.send_bytes(pcm_to_bytes([0.0] * 1920))
        ws.send_json({"type": "stop"})
        events = read_until(ws, "transcript_final")
    assert events[-1][1]["text"] == ""
    assert session.exec(select(Message)).all() == []


def test_expired_attempt_reports_error(voice_app, world, session):
    from datetime import datetime, timedelta
    world["attempt"].expires_at = datetime.utcnow() - timedelta(seconds=1)
    session.add(world["attempt"])
    session.commit()
    client, _ = voice_app()
    with client.websocket_connect(url(world)) as ws:
        ws.receive_json()
        speak(ws)
        events = read_until(ws, "error")
    assert events[-1][1]["status"] == 408


def test_rejects_unauthenticated(voice_app, world, monkeypatch):
    client, _ = voice_app()

    async def nobody(websocket):
        return None
    monkeypatch.setattr(voice_routes, "_authenticate", nobody)
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect(url(world)) as ws:
            ws.receive_json()
    assert exc.value.code == 1008


def test_rejects_foreign_origin(voice_app, world):
    client, _ = voice_app()
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(url(world), headers={"origin": "https://site-malveillant.example"}) as ws:
            ws.receive_json()
    # Même origine : accepté
    with client.websocket_connect(url(world), headers={"origin": "http://testserver"}) as ws:
        assert ws.receive_json()["type"] == "ready"


def test_rejects_other_users_attempt(voice_app, world, session):
    from models import User
    client, _ = voice_app()
    other = User(username="autre", hashed_password="x")
    session.add(other)
    session.commit()

    async def someone_else(websocket):
        return other
    voice_routes._authenticate = someone_else  # remis par monkeypatch du fixture à la fin
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(url(world)) as ws:
            ws.receive_json()


# ==================== Consultation mains libres ====================

SEG_QUESTION = ["Depuis", "quand", "avez-vous", "mal", "?"]


def converse(ws):
    assert ws.receive_json()["type"] == "ready"
    ws.send_json({"type": "conversation_start"})
    read_until(ws, "listening")


def say(ws, speech_frames=12, silence_frames=6):
    """L'étudiant parle puis se tait (le faux STT prononce le segment suivant)."""
    for _ in range(speech_frames):
        ws.send_bytes(pcm_to_bytes(speech_frame()))
    for _ in range(silence_frames):
        ws.send_bytes(pcm_to_bytes([0.0] * 1920))


def student_messages(session, world):
    rows = session.exec(select(Message).where(Message.attempt_id == world["attempt"].id)
                        .order_by(Message.created_at)).all()
    return [(r.role, r.content) for r in rows]


def test_hands_free_turn_without_button(voice_app, world, session):
    client, _ = voice_app(segments=[SEG_QUESTION])
    with client.websocket_connect(url(world)) as ws:
        converse(ws)
        say(ws)  # pas de "stop" : la fin de phrase est détectée par la pause
        events = read_until(ws, "audio_end")
    kinds = [k for k, _ in events]
    assert next(d for k, d in events if k == "transcript_final")["text"] == "Depuis quand avez-vous mal ?"
    assert "".join(d["text"] for k, d in events if k == "delta") == REPLY
    assert kinds.count("audio") == 6
    assert student_messages(session, world) == [
        (ChatRole.student, "Depuis quand avez-vous mal ?"), (ChatRole.patient, REPLY)]


def test_hands_free_barge_in_by_voice(voice_app, world, session):
    client, _ = voice_app(segments=[SEG_QUESTION, ["Pardon", "je", "reprends"]], tts_frame_delay=0.3)
    with client.websocket_connect(url(world)) as ws:
        converse(ws)
        say(ws)
        read_until(ws, "audio")
        ws.send_json({"type": "playback", "state": "started"})  # le navigateur joue la voix
        say(ws)                                                 # l'étudiant parle par-dessus
        events = read_until(ws, "transcript_final")
        ws.send_json({"type": "playback", "state": "ended"})
        read_until(ws, "done")
    kinds = [k for k, _ in events]
    assert "interrupted" in kinds
    assert kinds.index("interrupted") < kinds.index("transcript_final")
    assert events[-1][1]["text"] == "Pardon je reprends"
    # La réplique coupée est enregistrée, puis le nouvel échange
    assert student_messages(session, world) == [
        (ChatRole.student, "Depuis quand avez-vous mal ?"), (ChatRole.patient, REPLY),
        (ChatRole.student, "Pardon je reprends"), (ChatRole.patient, REPLY)]


def test_hands_free_ignores_echo_of_patient_voice(voice_app, world, session):
    echo = ["Ça", "a", "commencé", "devant"]  # le micro entend la voix du patient
    client, _ = voice_app(segments=[SEG_QUESTION, echo, ["Vous", "fumez", "?"]], tts_frame_delay=0.05)
    with client.websocket_connect(url(world)) as ws:
        converse(ws)
        say(ws)
        read_until(ws, "audio")
        ws.send_json({"type": "playback", "state": "started"})
        say(ws)                                    # écho : ne doit ni couper ni compter
        read_until(ws, "audio_end")
        ws.send_json({"type": "playback", "state": "ended"})
        say(ws)                                    # vraie question suivante
        events = read_until(ws, "transcript_final")
        read_until(ws, "done")
    kinds = [k for k, _ in events]
    assert "interrupted" not in kinds
    assert events[-1][1]["text"] == "Vous fumez ?"
    assert [c for r, c in student_messages(session, world) if r == ChatRole.student] == [
        "Depuis quand avez-vous mal ?", "Vous fumez ?"]


def test_hands_free_false_start_is_merged(voice_app, world, session, monkeypatch):
    client, _ = voice_app(segments=[["Depuis", "quand"], ["avez-vous", "mal", "?"]])

    async def slow_agent(**kwargs):
        await asyncio.sleep(1.0)  # le patient réfléchit encore quand l'étudiant reprend
        yield ("delta", "Oui.")
        yield ("done", PatientAgentResult(reply="Oui."))
    monkeypatch.setattr(chat_routes, "stream_patient_agent", slow_agent)

    with client.websocket_connect(url(world)) as ws:
        converse(ws)
        say(ws, speech_frames=4, silence_frames=10)  # > 12 mesures : au-delà de l'échauffement
        first = read_until(ws, "transcript_final")
        say(ws, speech_frames=6)               # l'étudiant n'avait pas fini sa phrase
        events = read_until(ws, "transcript_final")
        read_until(ws, "done")
    assert first[-1][1]["text"] == "Depuis quand"
    assert "turn_cancelled" in [k for k, _ in events]
    assert events[-1][1]["text"] == "Depuis quand avez-vous mal ?"
    # Une seule question enregistrée, complète
    assert student_messages(session, world) == [
        (ChatRole.student, "Depuis quand avez-vous mal ?"), (ChatRole.patient, "Oui.")]


def test_hands_free_fallback_endpoint_without_pause_prediction(voice_app, world):
    client, _ = voice_app(segments=[SEG_QUESTION], pause_after_frames=10_000)  # le modèle ne prédit jamais la pause
    with client.websocket_connect(url(world)) as ws:
        converse(ws)
        say(ws, silence_frames=30)
        events = read_until(ws, "transcript_final")
    assert events[-1][1]["text"] == "Depuis quand avez-vous mal ?"


def test_hands_free_stt_unavailable(voice_app, world):
    client, _ = voice_app(stt_error="at capacity")
    with client.websocket_connect(url(world)) as ws:
        ws.receive_json()
        ws.send_json({"type": "conversation_start"})
        events = read_until(ws, "error")
    assert events[-1][1]["status"] == 503


def test_hands_free_stop(voice_app, world, session):
    client, _ = voice_app(segments=[SEG_QUESTION])
    with client.websocket_connect(url(world)) as ws:
        converse(ws)
        ws.send_json({"type": "conversation_stop"})
        read_until(ws, "conversation_stopped")
        say(ws)  # micro fermé côté serveur : rien n'est transcrit
        ws.send_json({"type": "conversation_start"})
        events = read_until(ws, "listening")
    assert [k for k, _ in events] == ["listening"]
    assert session.exec(select(Message)).all() == []
