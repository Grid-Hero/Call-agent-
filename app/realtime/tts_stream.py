"""Streaming-Text-to-Speech für den Echtzeit-Modus.

Liefert μ-law-8 kHz-Audio in Chunks – genau das Format, das Twilio Media Streams
erwartet. So kann der Agent zu sprechen beginnen, bevor der ganze Text vertont
ist (geringe Latenz), und die Wiedergabe ist für Barge-in abbrechbar.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import AsyncIterator

import httpx

from app.config import Settings

logger = logging.getLogger(__name__)

_API_BASE = "https://api.elevenlabs.io/v1/text-to-speech"
# μ-law 8 kHz – Twilios natives Format (kein Transcoding nötig).
_REALTIME_FORMAT = "ulaw_8000"


class StreamingTTS(ABC):
    @abstractmethod
    def stream(self, text: str, language: str) -> AsyncIterator[bytes]:
        """Liefert μ-law-Audio-Chunks für ``text``."""


class ElevenLabsStreamingTTS(StreamingTTS):
    def __init__(self, settings: Settings):
        self.settings = settings

    async def stream(self, text: str, language: str) -> AsyncIterator[bytes]:
        if not text or not text.strip():
            return
        if not (self.settings.elevenlabs_api_key and self.settings.elevenlabs_voice_id):
            logger.warning("ElevenLabs nicht konfiguriert – kein Echtzeit-Audio.")
            return

        url = f"{_API_BASE}/{self.settings.elevenlabs_voice_id}/stream"
        headers = {
            "xi-api-key": self.settings.elevenlabs_api_key,
            "accept": "audio/basic",
            "content-type": "application/json",
        }
        payload = {
            "text": text,
            "model_id": self.settings.elevenlabs_model,
            "voice_settings": {"stability": 0.5, "similarity_boost": 0.75},
        }
        params = {"output_format": _REALTIME_FORMAT}
        try:
            async with httpx.AsyncClient(timeout=None) as client:
                async with client.stream(
                    "POST", url, headers=headers, json=payload, params=params
                ) as resp:
                    resp.raise_for_status()
                    async for chunk in resp.aiter_bytes():
                        if chunk:
                            yield chunk
        except Exception:  # pragma: no cover - Netzwerk/API
            logger.exception("ElevenLabs-Streaming fehlgeschlagen")
            return
