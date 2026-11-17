# voice_routes.py
"""
Mode vocal « appuyer pour parler » : WebSocket /chat/attempts/{attempt_id}/voice

Un tour vocal suit exactement le même chemin qu'un tour écrit (_run_turn :
arbitre en parallèle, agent patient avec outils, persistance), avec la
reconnaissance vocale en entrée et la synthèse vocale en sortie.

Navigateur -> serveur
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
  {"type": "voice_unavailable", "message": ...}   synthèse indisponible : la réplique reste écrite
  {"type": "error", "status": ..., "message": ...}
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from contextlib import aclosing, suppress
from typing import Optional
from urllib.parse import urlparse
from uuid import UUID

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

import chat_routes
from auth import get_current_user
from kyutai_voice import (
    STTSession, TTSSession, VoiceServiceError, WordChunker,
    default_voice, pcm_from_bytes, pcm_to_bytes,
)
from models import Attempts, ChatIn, ClinicalCase, User

logger = logging.getLogger(__name__)

router = APIRouter()

STT_UNAVAILABLE = "La reconnaissance vocale est indisponible. Réessayez ou passez à l'écrit."
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
                    if self.stt is not None:
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
                    await self.interrupt()
        except WebSocketDisconnect:
            pass
        finally:
            await self.close()

    async def start_listening(self) -> None:
        # L'étudiant reprend la parole : la voix du patient est coupée
        await self.interrupt()
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
            self.turn_task = asyncio.create_task(self.respond(transcript, previous=self.turn_task))

    async def interrupt(self) -> None:
        """Coupe la VOIX du patient. Le texte de la réplique continue d'arriver et est
        enregistré : couper la parole ne fait jamais perdre un échange."""
        if self.speaker is not None and await self.speaker.stop():
            await self.send_json({"type": "interrupted"})

    async def close(self) -> None:
        # Déconnexion : comme en SSE, un tour non terminé n'est pas enregistré
        if self.turn_task is not None and not self.turn_task.done():
            self.turn_task.cancel()
            await asyncio.wait([self.turn_task])
        if self.stt is not None:
            await self.stt.cancel()

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
        try:
            async with aclosing(chat_routes._run_turn(turn, chat_routes._write_session)) as events:
                async for kind, value in events:
                    if kind == "delta":
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
                        if value.blocked:
                            # Message refusé : avertissement écrit, pas de voix
                            speaker.mark_done()
                            await self.send_json({"type": "done", **value.model_dump()})
                            return
                        await speaker.finish()
                        await self.send_json({"type": "done", **value.model_dump()})
                        await speaker.wait()  # la tâche vit jusqu'à la fin de la voix
                        return
        finally:
            speaker.mark_done()
            await speaker.close()
            if self.speaker is speaker:
                self.speaker = None


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
                await self.conversation.send_audio(pcm)
        except VoiceServiceError as e:
            logger.warning("⚠️ Synthèse vocale interrompue : %s", e)
        self._done = True
        await self.conversation.send_json({"type": "audio_end"})

    async def feed(self, text: str) -> None:
        words = self.chunker.feed(text)
        if words and await self._ready():
            for word in words:
                await self.tts.send_word(word)

    async def finish(self) -> None:
        words = self.chunker.flush()
        if await self._ready():
            for word in words:
                await self.tts.send_word(word)
            await self.tts.end()

    async def wait(self) -> None:
        if self._pump is not None and not self._muted:
            with suppress(asyncio.CancelledError):
                await asyncio.shield(self._pump)

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
