"""Erzeugt die Echtzeit-Komponenten (STT, Streaming-TTS, Anrufsteuerung)."""

from __future__ import annotations

from app.config import Settings
from app.realtime.call_control import CallControl, TwilioCallControl
from app.realtime.stt import DeepgramSTT, ElevenLabsSTT, StreamingSTT
from app.realtime.tts_stream import ElevenLabsStreamingTTS, StreamingTTS


def build_stt(settings: Settings) -> StreamingSTT:
    provider = (settings.stt_provider or "elevenlabs").lower()
    if provider == "elevenlabs":
        return ElevenLabsSTT(settings)
    if provider == "deepgram":
        return DeepgramSTT(settings)
    raise RuntimeError(f"Unbekannter STT_PROVIDER: {settings.stt_provider}")


def build_streaming_tts(settings: Settings) -> StreamingTTS:
    # Aktuell nur ElevenLabs für Echtzeit (μ-law-Streaming).
    return ElevenLabsStreamingTTS(settings)


def build_call_control(settings: Settings) -> CallControl:
    return TwilioCallControl(settings)
