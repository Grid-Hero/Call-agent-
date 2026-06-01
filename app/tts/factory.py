"""Wählt den TTS-Anbieter anhand der Konfiguration."""

from __future__ import annotations

import logging

from app.config import Settings
from app.tts.base import NullTTS, TTSProvider
from app.tts.store import AudioStore

logger = logging.getLogger(__name__)


def build_tts(settings: Settings, store: AudioStore) -> TTSProvider:
    provider = (settings.tts_provider or "twilio").lower()
    if provider == "elevenlabs":
        if settings.elevenlabs_api_key and settings.elevenlabs_voice_id:
            from app.tts.elevenlabs import ElevenLabsTTS

            logger.info("TTS-Anbieter: ElevenLabs (Voice %s)", settings.elevenlabs_voice_id)
            return ElevenLabsTTS(settings, store)
        logger.warning(
            "TTS_PROVIDER=elevenlabs, aber API-Key/Voice-ID fehlen – nutze Anbieter-Stimme."
        )
    return NullTTS()
