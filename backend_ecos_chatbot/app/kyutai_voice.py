# kyutai_voice.py
"""
Clients des serveurs vocaux Kyutai (moshi-server) : reconnaissance (STT) et
synthèse (TTS) vocales en flux, modèles kyutai/stt-1b-en_fr et kyutai/tts-1.6b-en_fr.

Protocole (WebSocket, messages msgpack, audio PCM float32 mono 24 kHz) :

STT  /api/asr-streaming
  -> {"type": "Audio", "pcm": [...]}          trames de 1920 échantillons (80 ms)
  -> {"type": "Marker", "id": n}              renvoyé quand tout l'audio précédent est traité
  <- Ready | Word{text, start_time} | EndWord{stop_time} | Step{step_idx, prs} | Marker{id} | Error
     (prs[2] = probabilité de pause, base de la détection sémantique de fin de phrase)

TTS  /api/tts_streaming?voice=<chemin dans kyutai/tts-voices>&format=PcmMessagePack
  -> {"type": "Text", "text": "<un mot>"}  ...  {"type": "Eos"}
  <- Ready | Audio{pcm} | Text{text, start_s, stop_s} | Error ; le serveur ferme après Eos

Référence : scripts de kyutai-labs/delayed-streams-modeling et client d'Unmute (MIT).
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
import sys
from array import array
from typing import AsyncIterator, Awaitable, Callable, List, Optional
from urllib.parse import urlencode

import msgpack
from websockets.asyncio.client import ClientConnection, connect
from websockets.exceptions import ConnectionClosed

logger = logging.getLogger(__name__)

SAMPLE_RATE = 24000
FRAME_SIZE = 1920  # 80 ms
STT_PATH = "/api/asr-streaming"
TTS_PATH = "/api/tts_streaming"

# Voix par défaut (chemins relatifs au dépôt Hugging Face kyutai/tts-voices)
DEFAULT_VOICE = "unmute-prod-website/developpeuse-3.wav"


class VoiceServiceError(Exception):
    """Serveur vocal injoignable, saturé ou en erreur."""


# ==================== CONFIGURATION ====================

def _ws_base(url: str) -> str:
    url = url.rstrip("/")
    if url.startswith("http://"):
        return "ws://" + url[len("http://"):]
    if url.startswith("https://"):
        return "wss://" + url[len("https://"):]
    return url


def stt_url() -> str:
    return _ws_base(os.getenv("KYUTAI_STT_URL", "ws://localhost:8090")) + STT_PATH


def tts_url(voice: str) -> str:
    params = {"voice": voice, "format": "PcmMessagePack"}
    cfg = os.getenv("KYUTAI_TTS_CFG_ALPHA")
    if cfg:
        params["cfg_alpha"] = cfg
    return _ws_base(os.getenv("KYUTAI_TTS_URL", "ws://localhost:8089")) + TTS_PATH + "?" + urlencode(params)


def _headers() -> dict:
    return {"kyutai-api-key": os.getenv("KYUTAI_API_KEY", "public_token")}


def default_voice() -> str:
    return os.getenv("KYUTAI_TTS_DEFAULT_VOICE", DEFAULT_VOICE)


# ==================== AUDIO ====================

def pcm_from_bytes(data: bytes) -> List[float]:
    """Trame binaire du navigateur (float32 little-endian) -> liste de floats."""
    samples = array("f")
    samples.frombytes(data[: len(data) - len(data) % 4])
    if sys.byteorder != "little":
        samples.byteswap()
    return samples.tolist()


def pcm_to_bytes(samples: List[float]) -> bytes:
    """Liste de floats -> trame binaire float32 little-endian pour le navigateur."""
    out = array("f", samples)
    if sys.byteorder != "little":
        out.byteswap()
    return out.tobytes()


def _pack(data: dict) -> bytes:
    return msgpack.packb(data, use_bin_type=True, use_single_float=True)


def _unpack(data: bytes) -> dict:
    return msgpack.unpackb(data, raw=False)


async def _wait_ready(ws: ClientConnection, service: str) -> None:
    # Quelques messages résiduels peuvent précéder Ready (cf. client Unmute)
    for _ in range(10):
        message = _unpack(await ws.recv(decode=False))
        if message.get("type") == "Ready":
            return
        if message.get("type") == "Error":
            raise VoiceServiceError(f"{service} : {message.get('message', 'erreur')}")
    raise VoiceServiceError(f"{service} : pas de message Ready")


# ==================== TEXTE POUR LA SYNTHÈSE ====================

_PUNCT_ONLY = re.compile(r"^[?!:;.,…»)\]]+$")


def prepare_text_for_tts(text: str) -> str:
    text = text.strip()
    for char in "*_`#":
        text = text.replace(char, "")
    text = text.replace("“", '"').replace("”", '"').replace("’", "'").replace("‘", "'")
    text = text.replace("…", "...")
    text = re.sub(r"(\d)\s*/\s*(\d)", r"\1 sur \2", text)  # "8/10" -> "8 sur 10"
    return text


class WordChunker:
    """Transforme le flux de morceaux de texte du LLM en mots entiers pour la synthèse.

    - un mot n'est émis que lorsque le mot suivant a commencé : il peut être
      incomplet ("commen" + "cé") ou suivi d'une ponctuation isolée ("ça ?") ;
    - la ponctuation isolée est rattachée au mot précédent ("ça ?" -> "ça?").
    """

    def __init__(self) -> None:
        self._buf = ""

    @staticmethod
    def _merge(tokens: List[str]) -> List[str]:
        merged: List[str] = []
        for token in tokens:
            if merged and _PUNCT_ONLY.match(token):
                merged[-1] += token
            else:
                merged.append(token)
        return merged

    def feed(self, text: str) -> List[str]:
        self._buf += text
        words = self._merge(self._buf.split())
        if not words:
            return []
        trailing = self._buf[len(self._buf.rstrip()):]
        self._buf = words[-1] + trailing
        return words[:-1]

    def flush(self) -> List[str]:
        words = self._merge(self._buf.split())
        self._buf = ""
        return words


# ==================== RECONNAISSANCE VOCALE ====================

class STTSession:
    """Une prise de parole : audio en flux -> mots, jusqu'au marqueur de fin.

    L'audio reçu avant que la connexion soit prête est mis en file d'attente :
    l'étudiant peut commencer à parler dès qu'il appuie sur le bouton.
    """

    def __init__(
        self,
        url: Optional[str] = None,
        on_word: Optional[Callable[[str], Awaitable[None]]] = None,
        connect_timeout: float = 5.0,
        max_tail_sec: float = 3.0,
    ) -> None:
        self.url = url or stt_url()
        self.on_word = on_word
        self.connect_timeout = connect_timeout
        self.max_tail_frames = int(max_tail_sec * SAMPLE_RATE / FRAME_SIZE)
        self.words: List[str] = []
        self.pause_probability: Optional[float] = None
        self.error: Optional[BaseException] = None
        self._queue: asyncio.Queue = asyncio.Queue()
        self._marker = asyncio.Event()
        self._task: Optional[asyncio.Task] = None

    @property
    def transcript(self) -> str:
        return " ".join(self.words).strip()

    def open(self) -> None:
        self._task = asyncio.create_task(self._run())

    def push_audio(self, samples: List[float]) -> None:
        if samples:
            self._queue.put_nowait(("audio", samples))

    async def finish(self, timeout: float = 8.0) -> str:
        """Fin de la prise de parole : attend les derniers mots puis ferme la connexion."""
        if self._task is None:
            raise RuntimeError("STTSession.open() n'a pas été appelé")
        self._queue.put_nowait(("marker", 1))
        try:
            await asyncio.wait_for(asyncio.shield(self._task), timeout)
        except asyncio.TimeoutError:
            self._task.cancel()
            raise VoiceServiceError("STT : délai dépassé en fin de prise de parole")
        if self.error is not None:
            if not self.words:
                raise VoiceServiceError(f"STT : {self.error}") from self.error
            logger.warning("⚠️ STT incomplet (%s), transcription partielle conservée", self.error)
        return self.transcript

    async def cancel(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
            await asyncio.wait([self._task])

    async def _run(self) -> None:
        try:
            async with connect(self.url, additional_headers=_headers(),
                               open_timeout=self.connect_timeout, max_size=None) as ws:
                await asyncio.wait_for(_wait_ready(ws, "STT"), self.connect_timeout)
                receiver = asyncio.create_task(self._receive(ws))
                try:
                    await self._send_loop(ws)
                    await asyncio.wait_for(self._marker.wait(), timeout=5.0)
                finally:
                    receiver.cancel()
                    await asyncio.wait([receiver])
        except asyncio.CancelledError:
            raise
        except (OSError, ConnectionClosed, asyncio.TimeoutError, VoiceServiceError) as e:
            self.error = e
            logger.warning("⚠️ STT : %s: %s", type(e).__name__, e)

    async def _send_loop(self, ws: ClientConnection) -> None:
        silence = [0.0] * FRAME_SIZE
        while True:
            kind, payload = await self._queue.get()
            if kind == "audio":
                await ws.send(_pack({"type": "Audio", "pcm": payload}))
            elif kind == "marker":
                await ws.send(_pack({"type": "Marker", "id": payload}))
                # Le marqueur ne revient qu'une fois l'audio qui le précède transcrit,
                # en tenant compte du délai du modèle (~0,5 s) : on envoie du silence
                # (plus vite que le temps réel) jusqu'à son retour.
                for _ in range(self.max_tail_frames):
                    if self._marker.is_set():
                        break
                    await ws.send(_pack({"type": "Audio", "pcm": silence}))
                    await asyncio.sleep(0.01)
                return

    async def _receive(self, ws: ClientConnection) -> None:
        try:
            async for raw in ws:
                message = _unpack(raw)
                kind = message.get("type")
                if kind == "Word":
                    text = str(message.get("text", "")).strip()
                    if text:
                        self.words.append(text)
                        if self.on_word:
                            await self.on_word(text)
                elif kind == "Step":
                    prs = message.get("prs") or []
                    if len(prs) > 2:
                        self.pause_probability = float(prs[2])
                elif kind == "Marker":
                    return
                elif kind == "Error":
                    self.error = VoiceServiceError(str(message.get("message", "erreur STT")))
                    return
            self.error = self.error or VoiceServiceError("connexion fermée avant la fin")
        except ConnectionClosed as e:
            self.error = e
        finally:
            self._marker.set()  # débloque l'envoi et finish(), même en cas d'erreur


class STTStream:
    """Reconnaissance en continu (consultation mains libres) : une seule connexion pour
    toute la consultation. Les mots, les probabilités de pause et les marqueurs sont
    remontés par des fonctions de rappel ; c'est l'appelant qui décide des fins de phrase.
    """

    # Silence injecté après un marqueur : délai du modèle (0,5 s) + marge (cf. Unmute)
    FLUSH_FRAMES = int(0.5 * SAMPLE_RATE / FRAME_SIZE) + 2

    def __init__(
        self,
        url: Optional[str] = None,
        on_word: Optional[Callable[[str], Awaitable[None]]] = None,
        on_step: Optional[Callable[[float], Awaitable[None]]] = None,
        on_marker: Optional[Callable[[int], Awaitable[None]]] = None,
        connect_timeout: float = 5.0,
    ) -> None:
        self.url = url or stt_url()
        self.on_word = on_word
        self.on_step = on_step
        self.on_marker = on_marker
        self.connect_timeout = connect_timeout
        self.error: Optional[BaseException] = None
        self.ready = asyncio.Event()
        self.closed = asyncio.Event()
        self._queue: asyncio.Queue = asyncio.Queue()
        self._task: Optional[asyncio.Task] = None

    def open(self) -> None:
        self._task = asyncio.create_task(self._run())

    async def wait_ready(self, timeout: float = 6.0) -> None:
        """Attend la connexion ; lève VoiceServiceError si le serveur est injoignable."""
        waiters = [asyncio.ensure_future(self.ready.wait()), asyncio.ensure_future(self.closed.wait())]
        _, pending = await asyncio.wait(waiters, timeout=timeout, return_when=asyncio.FIRST_COMPLETED)
        for waiter in pending:
            waiter.cancel()
        if not self.ready.is_set():
            raise VoiceServiceError(f"STT : {self.error or 'pas de connexion'}")

    def push_audio(self, samples: List[float]) -> None:
        if samples and not self.closed.is_set():
            self._queue.put_nowait(("audio", samples))

    def flush(self, marker_id: int) -> None:
        """Fin de phrase détectée : marqueur + silence, pour obtenir les derniers mots
        sans attendre le délai du modèle en temps réel."""
        self._queue.put_nowait(("marker", marker_id))
        silence = [0.0] * FRAME_SIZE
        for _ in range(self.FLUSH_FRAMES):
            self._queue.put_nowait(("audio", silence))

    async def close(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
            await asyncio.wait([self._task])

    async def _run(self) -> None:
        try:
            async with connect(self.url, additional_headers=_headers(),
                               open_timeout=self.connect_timeout, max_size=None) as ws:
                await asyncio.wait_for(_wait_ready(ws, "STT"), self.connect_timeout)
                self.ready.set()
                receiver = asyncio.create_task(self._receive(ws))
                try:
                    while not receiver.done():
                        getter = asyncio.ensure_future(self._queue.get())
                        await asyncio.wait([getter, receiver], return_when=asyncio.FIRST_COMPLETED)
                        if not getter.done():
                            getter.cancel()
                            break
                        kind, payload = getter.result()
                        if kind == "audio":
                            await ws.send(_pack({"type": "Audio", "pcm": payload}))
                        else:
                            await ws.send(_pack({"type": "Marker", "id": payload}))
                    if receiver.done() and receiver.exception():
                        raise receiver.exception()
                finally:
                    receiver.cancel()
                    await asyncio.wait([receiver])
        except asyncio.CancelledError:
            raise
        except (OSError, ConnectionClosed, asyncio.TimeoutError, VoiceServiceError) as e:
            self.error = e
            logger.warning("⚠️ STT (continu) : %s: %s", type(e).__name__, e)
        finally:
            self.closed.set()

    async def _receive(self, ws: ClientConnection) -> None:
        async for raw in ws:
            message = _unpack(raw)
            kind = message.get("type")
            if kind == "Word":
                text = str(message.get("text", "")).strip()
                if text and self.on_word:
                    await self.on_word(text)
            elif kind == "Step":
                prs = message.get("prs") or []
                if len(prs) > 2 and self.on_step:
                    await self.on_step(float(prs[2]))
            elif kind == "Marker":
                if self.on_marker:
                    await self.on_marker(int(message.get("id", 0)))
            elif kind == "Error":
                raise VoiceServiceError(str(message.get("message", "erreur STT")))


# ==================== SYNTHÈSE VOCALE ====================

class TTSSession:
    """Une réplique : mots en flux -> audio en flux."""

    def __init__(self, voice: Optional[str] = None, url: Optional[str] = None, connect_timeout: float = 5.0) -> None:
        self.voice = voice or default_voice()
        self.url = url or tts_url(self.voice)
        self.connect_timeout = connect_timeout
        self.samples_received = 0
        self._ws: Optional[ClientConnection] = None
        self._ended = False

    async def open(self) -> None:
        try:
            self._ws = await connect(self.url, additional_headers=_headers(),
                                     open_timeout=self.connect_timeout, max_size=None)
            await asyncio.wait_for(_wait_ready(self._ws, "TTS"), self.connect_timeout)
        except (OSError, ConnectionClosed, asyncio.TimeoutError) as e:
            await self.close()
            raise VoiceServiceError(f"TTS : {type(e).__name__}: {e}") from e
        except VoiceServiceError:
            await self.close()
            raise

    async def send_word(self, word: str) -> None:
        text = prepare_text_for_tts(word)
        if text and self._ws is not None and not self._ended:
            await self._ws.send(_pack({"type": "Text", "text": text}))

    async def end(self) -> None:
        if self._ws is not None and not self._ended:
            self._ended = True
            await self._ws.send(_pack({"type": "Eos"}))

    async def audio(self) -> AsyncIterator[List[float]]:
        """Trames audio jusqu'à la fermeture par le serveur (après Eos)."""
        if self._ws is None:
            raise RuntimeError("TTSSession.open() n'a pas été appelé")
        try:
            async for raw in self._ws:
                message = _unpack(raw)
                kind = message.get("type")
                if kind == "Audio":
                    pcm = message.get("pcm") or []
                    self.samples_received += len(pcm)
                    yield pcm
                elif kind == "Error":
                    raise VoiceServiceError(f"TTS : {message.get('message', 'erreur')}")
        except ConnectionClosed:
            pass

    async def close(self) -> None:
        if self._ws is not None:
            ws, self._ws = self._ws, None
            await ws.close()
