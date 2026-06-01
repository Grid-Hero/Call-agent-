"""ElevenLabs-TTS: synthetisiert Antworttexte zu Audio und liefert eine URL."""

from __future__ import annotations

import logging
from typing import Optional

import httpx

from app.config import Settings
from app.tts.base import TTSProvider
from app.tts.store import AudioStore

logger = logging.getLogger(__name__)

_API_BASE = "https://api.elevenlabs.io/v1/text-to-speech"


class ElevenLabsTTS(TTSProvider):
    def __init__(self, settings: Settings, store: AudioStore):
        self.settings = settings
        self.store = store
        self.base_url = settings.effective_base_url

    async def synthesize(self, text: str, language: str) -> Optional[str]:
        if not text or not text.strip():
            return None
        if not (self.settings.elevenlabs_api_key and self.settings.elevenlabs_voice_id):
            logger.warning("ElevenLabs nicht vollständig konfiguriert – nutze Anbieter-Stimme.")
            return None

        url = f"{_API_BASE}/{self.settings.elevenlabs_voice_id}"
        headers = {
            "xi-api-key": self.settings.elevenlabs_api_key,
            "accept": "audio/mpeg",
            "content-type": "application/json",
        }
        payload = {
            "text": text,
            "model_id": self.settings.elevenlabs_model,
            "voice_settings": {"stability": 0.5, "similarity_boost": 0.75},
        }
        params = {"output_format": self.settings.elevenlabs_output_format}
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(url, headers=headers, json=payload, params=params)
                resp.raise_for_status()
                token = self.store.put(resp.content, "audio/mpeg")
                return f"{self.base_url}/audio/{token}.mp3"
        except Exception:  # pragma: no cover - Netzwerk/API
            logger.exception("ElevenLabs-TTS fehlgeschlagen – weiche auf Anbieter-Stimme aus")
            return None
