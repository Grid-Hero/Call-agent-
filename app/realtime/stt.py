"""Streaming-Spracherkennung (Speech-to-Text) für den Echtzeit-Modus.

Abstraktion + Deepgram-Implementierung. Deepgram akzeptiert μ-law 8 kHz direkt,
also ist kein Transcoding des Twilio-Audios nötig.
"""

from __future__ import annotations

import base64
import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import AsyncIterator
from urllib.parse import urlencode

import websockets

from app.config import Settings

logger = logging.getLogger(__name__)

_DEEPGRAM_URL = "wss://api.deepgram.com/v1/listen"
_ELEVENLABS_STT_URL = "wss://api.elevenlabs.io/v1/speech-to-text/realtime"


class STTEventType(str, Enum):
    TRANSCRIPT = "transcript"          # (Teil-)Transkript, ggf. final
    SPEECH_STARTED = "speech_started"  # VAD: Anrufer beginnt zu sprechen (Barge-in)
    UTTERANCE_END = "utterance_end"    # Äußerung abgeschlossen -> auswerten


@dataclass
class STTEvent:
    type: STTEventType
    text: str = ""
    is_final: bool = False


class StreamingSTT(ABC):
    """Push-basierter STT-Stream: Audio rein, Ereignisse raus."""

    @abstractmethod
    async def start(self) -> None: ...

    @abstractmethod
    async def send_audio(self, audio: bytes) -> None: ...

    @abstractmethod
    def events(self) -> AsyncIterator[STTEvent]: ...

    @abstractmethod
    async def aclose(self) -> None: ...


class DeepgramSTT(StreamingSTT):
    def __init__(self, settings: Settings):
        self.settings = settings
        self._ws = None

    def _url(self) -> str:
        params = {
            "encoding": "mulaw",
            "sample_rate": "8000",
            "channels": "1",
            "model": self.settings.deepgram_model,
            "language": self.settings.deepgram_language,
            "interim_results": "true",
            "smart_format": "true",
            "vad_events": "true",       # liefert SpeechStarted für Barge-in
            "utterance_end_ms": "1000",  # Äußerungsende nach 1 s Stille
            "endpointing": "300",
        }
        return f"{_DEEPGRAM_URL}?{urlencode(params)}"

    async def start(self) -> None:
        self._ws = await websockets.connect(
            self._url(),
            additional_headers={"Authorization": f"Token {self.settings.deepgram_api_key}"},
        )
        logger.info("Deepgram-STT verbunden")

    async def send_audio(self, audio: bytes) -> None:
        if self._ws is not None and audio:
            await self._ws.send(audio)

    async def events(self) -> AsyncIterator[STTEvent]:
        if self._ws is None:
            return
        async for raw in self._ws:
            try:
                msg = json.loads(raw)
            except (ValueError, TypeError):
                continue
            mtype = msg.get("type")
            if mtype == "SpeechStarted":
                yield STTEvent(STTEventType.SPEECH_STARTED)
            elif mtype == "UtteranceEnd":
                yield STTEvent(STTEventType.UTTERANCE_END)
            elif mtype == "Results":
                alt = (msg.get("channel", {}).get("alternatives") or [{}])[0]
                transcript = alt.get("transcript", "").strip()
                if transcript:
                    yield STTEvent(
                        STTEventType.TRANSCRIPT,
                        text=transcript,
                        is_final=bool(msg.get("is_final")),
                    )
                # speech_final markiert ebenfalls ein Äußerungsende.
                if msg.get("speech_final"):
                    yield STTEvent(STTEventType.UTTERANCE_END)

    async def aclose(self) -> None:
        if self._ws is not None:
            try:
                await self._ws.send(json.dumps({"type": "CloseStream"}))
                await self._ws.close()
            except Exception:  # pragma: no cover
                pass
            self._ws = None


class ElevenLabsSTT(StreamingSTT):
    """ElevenLabs Scribe v2 Realtime – STT per WebSocket.

    Nimmt μ-law 8 kHz direkt entgegen (Twilios Format). Ermöglicht, STT und TTS
    über denselben ElevenLabs-Account zu betreiben – kein separater Dienst.

    Hinweis: Die exakten Query-/Nachrichten-Felder können sich mit der
    ElevenLabs-API ändern. Modell/Encoding sind über die Settings einstellbar,
    sodass eine Anpassung ohne Code-Änderung möglich ist.
    """

    def __init__(self, settings: Settings):
        self.settings = settings
        self._ws = None
        self._speaking = False  # für einmaliges SPEECH_STARTED pro Äußerung

    def _url(self) -> str:
        params = {
            "model_id": self.settings.elevenlabs_stt_model,
            "encoding": self.settings.elevenlabs_stt_encoding,
            "sample_rate": "8000",
            "commit_strategy": "vad",      # Server segmentiert Äußerungen selbst
            "language_code": self.settings.stt_language,
        }
        return f"{_ELEVENLABS_STT_URL}?{urlencode(params)}"

    async def start(self) -> None:
        self._ws = await websockets.connect(
            self._url(),
            additional_headers={"xi-api-key": self.settings.elevenlabs_api_key},
        )
        logger.info("ElevenLabs-STT verbunden")

    async def send_audio(self, audio: bytes) -> None:
        if self._ws is not None and audio:
            await self._ws.send(
                json.dumps(
                    {
                        "message_type": "input_audio_chunk",
                        "audio_base_64": base64.b64encode(audio).decode("ascii"),
                    }
                )
            )

    async def events(self) -> AsyncIterator[STTEvent]:
        if self._ws is None:
            return
        async for raw in self._ws:
            try:
                msg = json.loads(raw)
            except (ValueError, TypeError):
                continue
            mtype = msg.get("message_type")
            text = (msg.get("text") or "").strip()

            if mtype == "partial_transcript":
                # Erstes Teil-Transkript einer Äußerung -> Barge-in auslösen.
                if text and not self._speaking:
                    self._speaking = True
                    yield STTEvent(STTEventType.SPEECH_STARTED)
            elif mtype in ("committed_transcript", "final_transcript", "transcript"):
                if text:
                    yield STTEvent(STTEventType.TRANSCRIPT, text=text, is_final=True)
                self._speaking = False
                yield STTEvent(STTEventType.UTTERANCE_END)

    async def aclose(self) -> None:
        if self._ws is not None:
            try:
                await self._ws.send(json.dumps({"message_type": "close"}))
                await self._ws.close()
            except Exception:  # pragma: no cover
                pass
            self._ws = None
