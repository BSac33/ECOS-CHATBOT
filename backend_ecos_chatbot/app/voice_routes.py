# voice_routes.py
"""
Mode vocal « appuyer pour parler » : WebSocket /chat/attempts/{attempt_id}/voice

Un tour vocal suit exactement le même chemin qu'un tour écrit (_run_turn :
arbitre en parallèle, agent patient avec outils, persistance), avec la
reconnaissance vocale en entrée et la synthèse vocale en sortie.

Deux façons de parler :
- appuyer pour parler : "start" / "stop" délimitent chaque prise de parole ;
- consultation mains libres : "conversation_start" ouvre le micro en continu ; la fin
  de chaque phrase est détectée par le modèle (probabilité de pause), l'étudiant peut
  couper la parole au patient en parlant, et un faux départ est rattrapé.

Navigateur -> serveur
  {"type": "conversation_start"} / {"type": "conversation_stop"}   mains libres
  {"type": "playback", "state": "started"|"ended"}   la voix du patient joue / s'est tue
  {"type": "start"}          début de prise de parole (coupe le patient s'il parle)
  binaire                    audio du micro : PCM float32 little-endian, mono, 24 kHz
  {"type": "stop"}           fin de prise de parole -> transcription -> réplique du patient
  {"type": "interrupt"}      couper la voix du patient

Serveur -> navigateur
  {"type": "ready", "voice": "..."}               connexion prête
  {"type": "listening"}                           la reconnaissance vocale écoute
  {"type": "transcript_partial", "text": "..."}   sous-titres en direct
  {"type": "transcript_final", "text": "..."}     texte vide = rien entendu
  {"type": "delta", "text": "..."}                réplique du patient (texte)
  {"type": "examiner_note", ...ExaminerNoteOut}
  {"type": "done", ...ChatOut}                    réplique enregistrée en base
  binaire                                         voix du patient : PCM float32 LE, mono, 24 kHz
  {"type": "audio_end"}                           fin de la voix de la réplique
  {"type": "interrupted"}                         voix du patient coupée
  {"type": "turn_cancelled"}                      faux départ : l'étudiant a repris avant
                                                  que le patient parle, la phrase continue
  {"type": "patient_interrupted", "message_id", "reason", "spoken_content"}
                                                  coupure de parole enregistrée (faute en ECOS)
  {"type": "voice_unavailable", "message": ...}   synthèse indisponible : la réplique reste écrite
  {"type": "error", "status": ..., "message": ...}
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
from contextlib import aclosing, suppress
from typing import Optional
from urllib.parse import urlparse
from uuid import UUID

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

import chat_routes
from auth import get_current_user
from arbiter import normalize
from kyutai_voice import (
    SAMPLE_RATE, STTSession, STTStream, TTSSession, VoiceServiceError, WordChunker,
    default_voice, pcm_from_bytes, pcm_to_bytes, prepare_text_for_tts,
)
from models import Attempts, ChatIn, ClinicalCase, Message, User

logger = logging.getLogger(__name__)

router = APIRouter()

STT_UNAVAILABLE = "La reconnaissance vocale est indisponible. Réessayez ou passez à l'écrit."

# Consultation mains libres (seuils de détection repris d'Unmute)
PAUSE_THRESHOLD = 0.6          # probabilité de pause au-delà de laquelle la phrase est finie
PAUSE_WARMUP_STEPS = 12        # premières prédictions instables, ignorées
ENDPOINT_FALLBACK_STEPS = 25   # 2 s sans nouveau mot : fin de phrase forcée
BARGE_IN_MIN_WORDS = 2         # mots (hors écho) nécessaires pour couper la parole au patient
ECHO_TAIL_SEC = 1.5            # le micro peut encore entendre la fin de la voix (délai STT ~0,5 s)


# Marge de démarrage de la lecture côté navigateur (voir services/voice.ts)
PLAYBACK_START_MARGIN_SEC = 0.05


def _reply_words(text: str) -> list:
    """Mots d'une réplique, découpés comme pour la synthèse vocale."""
    chunker = WordChunker()
    return [w for w in chunker.feed(text) + chunker.flush() if prepare_text_for_tts(w)]


def _echo_key(word: str) -> str:
    return re.sub(r"[^\w]", "", normalize(word))
TTS_UNAVAILABLE = "La voix du patient est indisponible : sa réponse s'affiche par écrit."


# ==================== SÉCURITÉ DE LA CONNEXION ====================

def _origin_allowed(websocket: WebSocket) -> bool:
    """Protection contre le détournement de WebSocket entre sites (le cookie part
    avec la poignée de main) : même origine ou origine autorisée par CORS."""
    origin = websocket.headers.get("origin")
    if not origin:
        return True  # client hors navigateur (CLI, tests)
    if urlparse(origin).netloc == websocket.headers.get("host"):
        return True
    allowed = os.getenv("CORS_ORIGINS", "http://localhost:3000,http://localhost:5173").split(",")
    return origin in [o.strip() for o in allowed]


async def _authenticate(websocket: WebSocket) -> Optional[User]:
    token = websocket.cookies.get("access_token")
    if not token:
        authorization = websocket.headers.get("authorization", "")
        if authorization.lower().startswith("bearer "):
            token = authorization[7:]
    if not token:
        return None
    with chat_routes._write_session() as session:
        try:
            return await get_current_user(session=session, token=token)
        except HTTPException:
            return None


# ==================== CONVERSATION ====================

class VoiceConversation:
    def __init__(self, websocket: WebSocket, attempt_id: UUID, user: User, voice: str):
        self.ws = websocket
        self.attempt_id = attempt_id
        self.user = user
        self.voice = voice
        self.stt: Optional[STTSession] = None
        self.turn_task: Optional[asyncio.Task] = None
        self.speaker: Optional["_Speaker"] = None
        self._send_lock = asyncio.Lock()
        self._saved_turns: set = set()       # tours dont la réplique est enregistrée
        # Consultation mains libres
        self.stream: Optional[STTStream] = None
        self.state = "idle"                  # idle | waiting | user_speaking | flushing | responding
        self.utterance: list = []
        self.last_utterance: list = []
        self.steps_seen = 0
        self.steps_since_word = 0
        self.marker_id = 0
        self.barge_candidates: list = []
        # Voix du patient côté navigateur (rapportée par le client) et filtre d'écho
        self.playing = False
        self.playback_started_at: Optional[float] = None
        self.echo_until = 0.0
        self.reply_text = ""
        self.echo_vocab: set = set()

    # ---------- envoi (plusieurs tâches écrivent sur la même connexion) ----------

    async def send_json(self, data: dict) -> None:
        async with self._send_lock:
            if self.ws.client_state == WebSocketState.CONNECTED:
                with suppress(WebSocketDisconnect, RuntimeError):  # client parti entre-temps
                    await self.ws.send_text(json.dumps(data, ensure_ascii=False))

    async def send_audio(self, pcm: list) -> None:
        async with self._send_lock:
            if self.ws.client_state == WebSocketState.CONNECTED:
                with suppress(WebSocketDisconnect, RuntimeError):
                    await self.ws.send_bytes(pcm_to_bytes(pcm))

    # ---------- boucle principale ----------

    async def run(self) -> None:
        await self.send_json({"type": "ready", "voice": self.voice})
        try:
            while True:
                message = await self.ws.receive()
                if message["type"] == "websocket.disconnect":
                    break
                if message.get("bytes") is not None:
                    if self.stream is not None:
                        self.stream.push_audio(pcm_from_bytes(message["bytes"]))
                    elif self.stt is not None:
                        self.stt.push_audio(pcm_from_bytes(message["bytes"]))
                    continue
                try:
                    data = json.loads(message.get("text") or "{}")
                except json.JSONDecodeError:
                    continue
                kind = data.get("type")
                if kind == "start":
                    await self.start_listening()
                elif kind == "stop":
                    await self.stop_listening()
                elif kind == "interrupt":
                    await self.interrupt("button")
                elif kind == "conversation_start":
                    await self.start_conversation()
                elif kind == "conversation_stop":
                    await self.stop_conversation()
                elif kind == "playback":
                    self.on_playback(data.get("state"))
        except WebSocketDisconnect:
            pass
        finally:
            await self.close()

    async def start_listening(self) -> None:
        # L'étudiant reprend la parole : la voix du patient est coupée
        await self.interrupt("push_to_talk")
        if self.stt is not None:
            await self.stt.cancel()

        async def on_word(_word: str) -> None:
            await self.send_json({"type": "transcript_partial", "text": stt.transcript})

        stt = STTSession(on_word=on_word)
        stt.open()
        self.stt = stt
        await self.send_json({"type": "listening"})

    async def stop_listening(self) -> None:
        stt, self.stt = self.stt, None
        if stt is None:
            return
        try:
            transcript = await stt.finish()
        except VoiceServiceError as e:
            logger.warning("⚠️ Reconnaissance vocale indisponible : %s", e)
            await self.send_json({"type": "error", "status": 503, "message": STT_UNAVAILABLE})
            return
        await self.send_json({"type": "transcript_final", "text": transcript})
        if transcript:
            self._start_turn(transcript)

    def _start_turn(self, transcript: str) -> None:
        task = asyncio.create_task(self.respond(transcript, previous=self.turn_task))
        self.turn_task = task
        task.add_done_callback(self._turn_finished)

    def _turn_finished(self, task: asyncio.Task) -> None:
        self._saved_turns.discard(task)
        if task is self.turn_task and self.state == "responding":
            self.state = "waiting"

    async def interrupt(self, reason: str) -> None:
        """Coupe la VOIX du patient. Le texte de la réplique continue d'arriver et est
        enregistré : couper la parole ne fait jamais perdre un échange.

        En ECOS, on ne coupe pas la parole au patient : si des mots de sa réplique
        n'ont pas été prononcés, la coupure est enregistrée (raison, partie entendue).
        """
        speaker = self.speaker
        played = self._played_seconds(speaker)
        stopped = await speaker.stop() if speaker is not None else False
        if stopped or self.playing:  # le navigateur peut encore jouer de l'audio reçu
            if speaker is not None and played > 0:
                speaker.interruption = {"reason": reason, "heard": speaker.heard_count(played)}
                await self._save_interruption(speaker)
            self.playing = False
            self.playback_started_at = None
            self.echo_until = time.monotonic() + ECHO_TAIL_SEC
            await self.send_json({"type": "interrupted"})

    def _played_seconds(self, speaker: Optional["_Speaker"]) -> float:
        """Durée de voix réellement jouée par le navigateur au moment de la coupure."""
        now = time.monotonic()
        if self.playback_started_at is not None:
            played = now - self.playback_started_at
        elif speaker is not None and speaker.first_audio_at is not None:
            played = now - speaker.first_audio_at - PLAYBACK_START_MARGIN_SEC
        else:
            return 0.0
        if speaker is not None:
            played = min(played, speaker.audio_seconds)
        return max(0.0, played)

    async def _save_interruption(self, speaker: "_Speaker") -> None:
        """Enregistre la coupure sur le message du patient (dès qu'il est enregistré)."""
        info = speaker.interruption
        if not info or speaker.interruption_saved or speaker.message_id is None or speaker.final_words is None:
            return
        speaker.interruption_saved = True
        heard = speaker.final_words[: info["heard"]]
        if len(heard) >= len(speaker.final_words):
            return  # chevauchement sur le dernier mot : le patient avait fini
        spoken = (" ".join(heard) + " …").strip()
        with chat_routes._write_session() as session:
            message = session.get(Message, UUID(speaker.message_id))
            if message is None:
                return
            message.interrupted_by = info["reason"]
            message.spoken_content = spoken
            session.add(message)
            session.commit()
        logger.info("✂️ Patient coupé (%s) après %d/%d mots", info["reason"], len(heard), len(speaker.final_words))
        await self.send_json({"type": "patient_interrupted", "message_id": speaker.message_id,
                              "reason": info["reason"], "spoken_content": spoken})

    async def close(self) -> None:
        if self.stream is not None:
            await self.stream.close()
        # Déconnexion : comme en SSE, un tour non terminé n'est pas enregistré
        if self.turn_task is not None and not self.turn_task.done():
            self.turn_task.cancel()
            await asyncio.wait([self.turn_task])
        if self.stt is not None:
            await self.stt.cancel()

    # ---------- consultation mains libres ----------

    async def start_conversation(self) -> None:
        if self.stream is not None:
            return
        stream = STTStream(on_word=self._on_word, on_step=self._on_step, on_marker=self._on_marker)
        stream.open()
        try:
            await stream.wait_ready()
        except VoiceServiceError as e:
            logger.warning("⚠️ Reconnaissance vocale indisponible : %s", e)
            await stream.close()
            await self.send_json({"type": "error", "status": 503, "message": STT_UNAVAILABLE})
            return
        self.stream = stream
        self.state = "waiting"
        self.steps_seen = 0
        await self.send_json({"type": "listening"})

    async def stop_conversation(self) -> None:
        stream, self.stream = self.stream, None
        if stream is not None:
            await stream.close()
        self.state = "idle"
        self.utterance = []
        await self.send_json({"type": "conversation_stopped"})

    def on_playback(self, state: Optional[str]) -> None:
        if state == "started":
            self.playing = True
            self.playback_started_at = time.monotonic()
        elif state == "ended":
            self.playing = False
            self.playback_started_at = None
            self.echo_until = time.monotonic() + ECHO_TAIL_SEC
            self.barge_candidates = []

    def _patient_audible(self) -> bool:
        return self.playing or (self.speaker is not None and self.speaker.audible)

    def _is_echo(self, word: str) -> bool:
        """Le micro entend la voix du patient : on ignore les mots de sa propre réplique."""
        if not (self._patient_audible() or time.monotonic() < self.echo_until):
            return False
        key = _echo_key(word)
        return bool(key) and key in self.echo_vocab

    async def _begin_utterance(self, words: list) -> None:
        self.state = "user_speaking"
        self.utterance = list(words)
        self.steps_since_word = 0
        await self.send_json({"type": "transcript_partial", "text": " ".join(self.utterance)})

    async def _on_word(self, word: str) -> None:
        if self._is_echo(word):
            return
        if self._patient_audible() and self.state not in ("user_speaking", "flushing"):
            # L'étudiant parle pendant que le patient parle : il lui coupe la parole
            self.barge_candidates.append(word)
            if len(self.barge_candidates) < BARGE_IN_MIN_WORDS:
                return
            words, self.barge_candidates = self.barge_candidates, []
            logger.info("🗣️ L'étudiant coupe la parole au patient")
            await self.interrupt("voice")
            await self._begin_utterance(words)
            return
        if self.state == "responding":
            task = self.turn_task
            if task is not None and not task.done() and task not in self._saved_turns:
                # Faux départ : l'étudiant reprend avant que le patient ait parlé.
                # Rien n'est encore enregistré : on annule et on continue la même phrase.
                task.cancel()
                await asyncio.wait([task])
                await self.send_json({"type": "turn_cancelled"})
                await self._begin_utterance(self.last_utterance + [word])
                return
            await self.interrupt("voice")
            await self._begin_utterance([word])
            return
        if self.state == "waiting":
            await self._begin_utterance([word])
            return
        if self.state in ("user_speaking", "flushing"):
            self.utterance.append(word)
            self.steps_since_word = 0
            await self.send_json({"type": "transcript_partial", "text": " ".join(self.utterance)})

    async def _on_step(self, pause_probability: float) -> None:
        self.steps_seen += 1
        if self.state != "user_speaking" or self.stream is None:
            return
        self.steps_since_word += 1
        paused = self.steps_seen > PAUSE_WARMUP_STEPS and pause_probability > PAUSE_THRESHOLD
        if paused or self.steps_since_word > ENDPOINT_FALLBACK_STEPS:
            # Fin de phrase : marqueur + silence pour récupérer les derniers mots
            self.state = "flushing"
            self.marker_id += 1
            self.stream.flush(self.marker_id)

    async def _on_marker(self, marker_id: int) -> None:
        if self.state != "flushing" or marker_id != self.marker_id:
            return
        text = " ".join(self.utterance).strip()
        self.last_utterance, self.utterance = self.utterance, []
        if not text:
            self.state = "waiting"
            return
        self.state = "responding"
        await self.send_json({"type": "transcript_final", "text": text})
        self._start_turn(text)

    # ---------- une réplique du patient ----------

    async def respond(self, transcript: str, previous: Optional[asyncio.Task] = None) -> None:
        # La réplique précédente doit être enregistrée avant de construire l'historique
        if previous is not None and not previous.done():
            await asyncio.wait([previous])

        with chat_routes._write_session() as session:
            try:
                turn = chat_routes._prepare_turn(self.attempt_id, ChatIn(message=transcript),
                                                 session, self.user, modality="voice")
            except HTTPException as e:
                await self.send_json({"type": "error", "status": e.status_code, "message": e.detail})
                return

        speaker = _Speaker(self, self.voice)
        self.speaker = speaker
        self.reply_text = ""
        try:
            async with aclosing(chat_routes._run_turn(turn, chat_routes._write_session)) as events:
                async for kind, value in events:
                    if kind == "delta":
                        self.reply_text += value
                        self.echo_vocab = {_echo_key(w) for w in self.reply_text.split()} - {""}
                        await self.send_json({"type": "delta", "text": value})
                        await speaker.feed(value)
                    elif kind == "examiner_note":
                        await self.send_json({"type": "examiner_note", **value.model_dump()})
                    elif kind == "error":
                        speaker.mark_done()
                        status_code, message = value
                        await self.send_json({"type": "error", "status": status_code, "message": message})
                        return
                    elif kind == "done":
                        self._saved_turns.add(asyncio.current_task())
                        speaker.message_id = value.patient_message_id
                        speaker.final_words = _reply_words(value.patient_reply)
                        if value.blocked:
                            # Message refusé : avertissement écrit, pas de voix
                            speaker.mark_done()
                            await self.send_json({"type": "done", **value.model_dump()})
                            return
                        await speaker.finish()
                        await self.send_json({"type": "done", **value.model_dump()})
                        # Coupure survenue avant l'enregistrement de la réplique : rattachée
                        # maintenant (après "done", pour que le navigateur connaisse le message)
                        await self._save_interruption(speaker)
                        await speaker.wait()  # la tâche vit jusqu'à la fin de la voix
                        return
        finally:
            speaker.mark_done()
            await speaker.close()
            # self.speaker reste la dernière réplique : le navigateur peut encore la
            # jouer, et une coupure doit pouvoir lui être rattachée


class _Speaker:
    """Synthèse vocale d'une réplique : ouverte dès le début du tour, alimentée mot à mot."""

    def __init__(self, conversation: VoiceConversation, voice: str):
        self.conversation = conversation
        self.tts = TTSSession(voice=voice)
        self.chunker = WordChunker()
        self._opening = asyncio.create_task(self.tts.open())
        self._pump: Optional[asyncio.Task] = None
        self._available: Optional[bool] = None
        self._muted = False   # coupé par l'étudiant
        self._done = False    # plus aucune voix à venir pour cette réplique
        self._audio_started = False
        # Suivi de ce qui est prononcé, pour mesurer une éventuelle coupure
        self.words_sent: list = []           # mots envoyés à la synthèse, dans l'ordre
        self.samples_forwarded = 0
        self.first_audio_at: Optional[float] = None
        self.message_id: Optional[str] = None
        self.final_words: Optional[list] = None
        self.interruption: Optional[dict] = None
        self.interruption_saved = False

    async def _ready(self) -> bool:
        if self._muted:
            return False
        if self._available is None:
            try:
                await self._opening
                self._available = True
                self._pump = asyncio.create_task(self._forward_audio())
            except VoiceServiceError as e:
                logger.warning("⚠️ Synthèse vocale indisponible : %s", e)
                self._available = False
                await self.conversation.send_json({"type": "voice_unavailable", "message": TTS_UNAVAILABLE})
        return self._available and not self._muted

    async def _forward_audio(self) -> None:
        try:
            async for pcm in self.tts.audio():
                if not self._audio_started:
                    self._audio_started = True
                    self.first_audio_at = time.monotonic()
                self.samples_forwarded += len(pcm)
                await self.conversation.send_audio(pcm)
        except VoiceServiceError as e:
            logger.warning("⚠️ Synthèse vocale interrompue : %s", e)
        self._done = True
        await self.conversation.send_json({"type": "audio_end"})

    async def _say(self, word: str) -> None:
        if prepare_text_for_tts(word):
            self.words_sent.append(word)
            await self.tts.send_word(word)

    async def feed(self, text: str) -> None:
        words = self.chunker.feed(text)
        if words and await self._ready():
            for word in words:
                await self._say(word)

    async def finish(self) -> None:
        words = self.chunker.flush()
        if await self._ready():
            for word in words:
                await self._say(word)
            await self.tts.end()

    @property
    def audio_seconds(self) -> float:
        return self.samples_forwarded / SAMPLE_RATE

    def heard_count(self, played: float) -> int:
        """Nombre de mots (au moins commencés) dans les `played` premières secondes de voix."""
        timings = self.tts.word_timings
        if timings:
            count = sum(1 for _, start, _ in timings if start < played)
        elif self.audio_seconds > 0:
            count = int(len(self.words_sent) * min(1.0, played / self.audio_seconds))
        else:
            count = 0
        return min(count, len(self.words_sent))

    async def wait(self) -> None:
        if self._pump is not None and not self._muted:
            with suppress(asyncio.CancelledError):
                await asyncio.shield(self._pump)

    @property
    def audible(self) -> bool:
        """La voix a commencé et n'est ni finie ni coupée (côté serveur)."""
        return self._audio_started and not (self._muted or self._done)

    def mark_done(self) -> None:
        self._done = True

    async def stop(self) -> bool:
        """Coupe la voix. Retourne True s'il restait de la voix à jouer."""
        was_active = not (self._muted or self._done)
        self._muted = True
        self._done = True
        await self.close()
        return was_active

    async def close(self) -> None:
        for task in (self._opening, self._pump):
            if task is not None and not task.done():
                task.cancel()
                with suppress(asyncio.CancelledError, Exception):
                    await task
        await self.tts.close()


# ==================== ROUTE ====================

@router.websocket("/attempts/{attempt_id}/voice")
async def voice(websocket: WebSocket, attempt_id: UUID):
    if not _origin_allowed(websocket):
        await websocket.close(code=1008, reason="Origine non autorisée")
        return
    user = await _authenticate(websocket)
    if user is None:
        await websocket.close(code=1008, reason="Non authentifié")
        return
    with chat_routes._write_session() as session:
        attempt = session.get(Attempts, attempt_id)
        if not attempt or attempt.user_id != user.id:
            await websocket.close(code=1008, reason="Tentative introuvable")
            return
        case = session.get(ClinicalCase, attempt.case_id)
        voice_id = (case.voice_id if case else None) or default_voice()

    await websocket.accept()
    await VoiceConversation(websocket, attempt_id, user, voice_id).run()
