"""Tests des clients Kyutai (vrai WebSocket + msgpack, faux serveurs)."""
import asyncio
import time

import pytest
import pytest_asyncio

import kyutai_voice
from fake_kyutai import FakeKyutai, speech_frame
from kyutai_voice import (
    STTSession, TTSSession, VoiceServiceError, WordChunker,
    pcm_from_bytes, pcm_to_bytes, prepare_text_for_tts,
)


@pytest_asyncio.fixture
async def kyutai(monkeypatch):
    server = await FakeKyutai(words=["Depuis", "quand", "avez-vous", "mal", "?"]).start()
    monkeypatch.setenv("KYUTAI_STT_URL", server.url)
    monkeypatch.setenv("KYUTAI_TTS_URL", server.url.replace("ws://", "http://"))  # http:// accepté
    monkeypatch.setenv("KYUTAI_API_KEY", "cle-test")
    yield server
    await server.stop()


# ---------- Découpage du texte en mots ----------

def feed_all(chunks):
    chunker = WordChunker()
    out = []
    for c in chunks:
        out += chunker.feed(c)
    return out, chunker.flush()


@pytest.mark.parametrize("chunks,expected", [
    (["Ça a commen", "cé d'un coup", " ?"], ["Ça", "a", "commencé", "d'un", "coup?"]),
    (["J'ai mal ", "! Docteur"], ["J'ai", "mal!", "Docteur"]),
    (["  Bonjour", " docteur", "."], ["Bonjour", "docteur."]),
    (["Oui"], ["Oui"]),
    ([""], []),
])
def test_word_chunker(chunks, expected):
    ready, rest = feed_all(chunks)
    assert ready + rest == expected


def test_word_chunker_holds_last_word_until_next_starts():
    chunker = WordChunker()
    assert chunker.feed("Ça ") == []          # "Ça" peut encore être suivi d'une ponctuation
    assert chunker.feed("serre") == ["Ça"]    # le mot suivant a commencé
    assert chunker.flush() == ["serre"]


def test_prepare_text_for_tts():
    assert prepare_text_for_tts("**8/10**") == "8 sur 10"
    assert prepare_text_for_tts("l’étau…") == "l'étau..."


def test_pcm_roundtrip():
    samples = [0.0, 0.5, -0.25, 1.0]
    assert pcm_from_bytes(pcm_to_bytes(samples)) == samples
    assert pcm_from_bytes(pcm_to_bytes(samples) + b"\x00") == samples  # octets en trop ignorés


# ---------- Reconnaissance vocale ----------

@pytest.mark.asyncio
async def test_stt_streams_words_and_flushes_with_marker(kyutai):
    heard = []

    async def on_word(word):
        heard.append(word)

    stt = STTSession(on_word=on_word)
    stt.open()
    for _ in range(12):               # l'étudiant parle avant même que la connexion soit prête
        stt.push_audio(speech_frame())
    await asyncio.sleep(0.2)
    assert heard[:2] == ["Depuis", "quand"]  # sous-titres en direct pendant la parole

    started = time.perf_counter()
    transcript = await stt.finish()
    assert time.perf_counter() - started < 1.5
    assert transcript == "Depuis quand avez-vous mal ?"
    assert heard == ["Depuis", "quand", "avez-vous", "mal", "?"]
    assert kyutai.stt_api_keys == ["cle-test"]
    # du silence a été envoyé après le marqueur, le temps que le modèle rattrape son délai
    assert kyutai.stt_frames_after_marker >= 6
    assert stt.pause_probability is not None


@pytest.mark.asyncio
async def test_stt_server_at_capacity(monkeypatch):
    server = await FakeKyutai(stt_error="at capacity").start()
    monkeypatch.setenv("KYUTAI_STT_URL", server.url)
    try:
        stt = STTSession()
        stt.open()
        with pytest.raises(VoiceServiceError, match="capacity"):
            await stt.finish()
    finally:
        await server.stop()


@pytest.mark.asyncio
async def test_stt_unreachable(monkeypatch):
    monkeypatch.setenv("KYUTAI_STT_URL", "ws://127.0.0.1:9")  # port fermé
    stt = STTSession(connect_timeout=1.0)
    stt.open()
    with pytest.raises(VoiceServiceError):
        await stt.finish(timeout=3)


# ---------- Synthèse vocale ----------

@pytest.mark.asyncio
async def test_tts_word_by_word(kyutai):
    tts = TTSSession(voice="cml-tts/fr/12977_10625_000037-0001.wav")
    await tts.open()

    async def speak():
        for word in ["La", "douleur", "est", "à", "8/10."]:
            await tts.send_word(word)
        await tts.end()

    sender = asyncio.create_task(speak())
    frames = [frame async for frame in tts.audio()]
    await sender
    await tts.close()

    assert len(frames) == 5 and all(len(f) == 1920 for f in frames)
    assert tts.samples_received == 5 * 1920
    assert kyutai.tts_texts == ["La", "douleur", "est", "à", "8 sur 10."]
    assert kyutai.tts_eos == 1
    request = kyutai.tts_requests[0]
    assert request["voice"] == "cml-tts/fr/12977_10625_000037-0001.wav"
    assert request["format"] == "PcmMessagePack"
    assert request["api_key"] == "cle-test"


@pytest.mark.asyncio
async def test_tts_default_voice(kyutai, monkeypatch):
    monkeypatch.setenv("KYUTAI_TTS_DEFAULT_VOICE", "unmute-prod-website/fabieng-enhanced-v2.wav")
    tts = TTSSession()
    await tts.open()
    await tts.close()
    assert kyutai.tts_requests[0]["voice"] == "unmute-prod-website/fabieng-enhanced-v2.wav"


@pytest.mark.asyncio
async def test_tts_error_at_startup(monkeypatch):
    server = await FakeKyutai(tts_error="at capacity").start()
    monkeypatch.setenv("KYUTAI_TTS_URL", server.url)
    try:
        with pytest.raises(VoiceServiceError, match="capacity"):
            await TTSSession().open()
    finally:
        await server.stop()


def test_urls(monkeypatch):
    monkeypatch.setenv("KYUTAI_STT_URL", "https://voix.exemple.fr/")
    monkeypatch.setenv("KYUTAI_TTS_URL", "ws://tts:8080")
    assert kyutai_voice.stt_url() == "wss://voix.exemple.fr/api/asr-streaming"
    assert kyutai_voice.tts_url("a/b c.wav") == "ws://tts:8080/api/tts_streaming?voice=a%2Fb+c.wav&format=PcmMessagePack"
