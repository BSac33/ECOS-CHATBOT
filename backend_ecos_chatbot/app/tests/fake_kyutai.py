"""Faux serveurs Kyutai (moshi-server) parlant le vrai protocole WebSocket + msgpack.

Utilisés par les tests et par l'essai de bout en bout dans le navigateur, sans GPU.

- STT : renvoie des mots scriptés pendant que de l'audio « parlé » (non nul) arrive,
  puis renvoie le marqueur après ASR_DELAY_FRAMES trames supplémentaires (le délai du modèle).
  Chaque segment de parole (séparé par SEGMENT_GAP_FRAMES trames de silence) prononce la
  liste de mots suivante de `segments`. La probabilité de pause (Step.prs[2]) passe à 0,9
  après `pause_after_frames` trames de silence suivant de la parole, comme le modèle réel.
- TTS : renvoie une trame audio (bip à 440 Hz) par mot reçu, puis ferme après Eos.
"""
from __future__ import annotations

import asyncio
import math
from typing import List, Optional
from urllib.parse import parse_qs, urlparse

import msgpack
from websockets.asyncio.server import ServerConnection, serve

FRAME_SIZE = 1920
ASR_DELAY_FRAMES = 6  # ~0,5 s, comme kyutai/stt-1b-en_fr
SEGMENT_GAP_FRAMES = 6


def _pack(data: dict) -> bytes:
    return msgpack.packb(data, use_bin_type=True, use_single_float=True)


class FakeKyutai:
    def __init__(self, words: Optional[List[str]] = None, frames_per_word: int = 2,
                 stt_error: Optional[str] = None, tts_error: Optional[str] = None,
                 tts_frame_delay: float = 0.0, segments: Optional[List[List[str]]] = None,
                 pause_after_frames: int = 3):
        self.segments = segments or [words or ["Bonjour", "docteur."]]
        self.pause_after_frames = pause_after_frames
        self.frames_per_word = frames_per_word
        self.stt_error = stt_error
        self.tts_error = tts_error
        self.tts_frame_delay = tts_frame_delay
        # Observations pour les assertions
        self.stt_api_keys: List[str] = []
        self.stt_frames_received = 0
        self.stt_frames_after_marker = 0
        self.tts_requests: List[dict] = []
        self.tts_texts: List[str] = []
        self.tts_eos = 0
        self._server = None
        self.port: Optional[int] = None

    @property
    def url(self) -> str:
        return f"ws://127.0.0.1:{self.port}"

    async def start(self) -> "FakeKyutai":
        # close_timeout court : à l'arrêt, une connexion dont le client de test a déjà disparu
        # ne doit pas faire attendre la fermeture 10 s (délai par défaut de websockets)
        self._server = await serve(self._handler, "127.0.0.1", 0, max_size=None, close_timeout=0.5)
        self.port = self._server.sockets[0].getsockname()[1]
        return self

    async def stop(self) -> None:
        if self._server:
            self._server.close()
            await self._server.wait_closed()

    async def _handler(self, ws: ServerConnection) -> None:
        path = urlparse(ws.request.path)
        if path.path == "/api/asr-streaming":
            await self._stt(ws)
        elif path.path == "/api/tts_streaming":
            await self._tts(ws, parse_qs(path.query))

    async def _stt(self, ws: ServerConnection) -> None:
        self.stt_api_keys.append(ws.request.headers.get("kyutai-api-key", ""))
        if self.stt_error:
            await ws.send(_pack({"type": "Error", "message": self.stt_error}))
            return
        await ws.send(_pack({"type": "Ready"}))
        segment, speech_frames, emitted = -1, 0, 0
        silent_run, marker_id, after_marker = SEGMENT_GAP_FRAMES, None, 0

        def words() -> List[str]:
            return self.segments[min(segment, len(self.segments) - 1)] if segment >= 0 else []

        async for raw in ws:
            message = msgpack.unpackb(raw, raw=False)
            if message["type"] == "Audio":
                self.stt_frames_received += 1
                if any(abs(x) > 0.01 for x in message["pcm"]):  # > -40 dBFS : parole
                    if silent_run >= SEGMENT_GAP_FRAMES:  # nouveau segment de parole
                        segment, speech_frames, emitted = segment + 1, 0, 0
                    silent_run = 0
                    speech_frames += 1
                    if emitted < len(words()) and speech_frames >= (emitted + 1) * self.frames_per_word:
                        await ws.send(_pack({"type": "Word", "text": words()[emitted],
                                             "start_time": speech_frames * 0.08}))
                        emitted += 1
                else:
                    silent_run += 1
                pause = speech_frames > 0 and silent_run >= self.pause_after_frames
                await ws.send(_pack({"type": "Step", "step_idx": self.stt_frames_received,
                                     "prs": [0.0, 0.0, 0.9 if (pause or marker_id is not None) else 0.1, 0.0]}))
                if marker_id is not None:
                    after_marker += 1
                    self.stt_frames_after_marker = after_marker
                    if after_marker >= ASR_DELAY_FRAMES:
                        # Mots restants du segment (le modèle rattrape son retard), puis le
                        # marqueur ; rien si aucune parole n'a été entendue
                        while speech_frames and emitted < len(words()):
                            await ws.send(_pack({"type": "Word", "text": words()[emitted], "start_time": 0.0}))
                            emitted += 1
                        await ws.send(_pack({"type": "Marker", "id": marker_id}))
                        marker_id, after_marker = None, 0
            elif message["type"] == "Marker":
                marker_id = message["id"]

    async def _tts(self, ws: ServerConnection, query: dict) -> None:
        self.tts_requests.append({k: v[0] for k, v in query.items()}
                                 | {"api_key": ws.request.headers.get("kyutai-api-key", "")})
        if self.tts_error:
            await ws.send(_pack({"type": "Error", "message": self.tts_error}))
            return
        await ws.send(_pack({"type": "Ready"}))
        t = 0.0
        async for raw in ws:
            message = msgpack.unpackb(raw, raw=False)
            if message["type"] == "Text":
                self.tts_texts.append(message["text"])
                await ws.send(_pack({"type": "Text", "text": message["text"], "start_s": t, "stop_s": t + 0.08}))
                pcm = [0.2 * math.sin(2 * math.pi * 440 * i / 24000) for i in range(FRAME_SIZE)]
                if self.tts_frame_delay:
                    await asyncio.sleep(self.tts_frame_delay)
                await ws.send(_pack({"type": "Audio", "pcm": pcm}))
                t += 0.08
            elif message["type"] == "Eos":
                self.tts_eos += 1
                break
        # Comme moshi-server : fermeture après la dernière trame
        await ws.close()


def speech_frame(amplitude: float = 0.3) -> List[float]:
    return [amplitude * math.sin(2 * math.pi * 220 * i / 24000) for i in range(FRAME_SIZE)]
