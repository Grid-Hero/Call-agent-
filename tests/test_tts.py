"""Tests für den Audio-Store und die TTS-Anbieter-Auswahl."""

from __future__ import annotations

from app.config import Settings
from app.tts.base import NullTTS
from app.tts.factory import build_tts
from app.tts.store import AudioStore


def test_audio_store_roundtrip():
    store = AudioStore()
    token = store.put(b"abc123", "audio/mpeg")
    data, ctype = store.get(token)
    assert data == b"abc123"
    assert ctype == "audio/mpeg"
    assert store.get("unbekannt") is None


def test_audio_store_expiry():
    store = AudioStore(ttl_seconds=-1)  # sofort abgelaufen
    token = store.put(b"x")
    assert store.get(token) is None


def test_factory_defaults_to_null_without_keys():
    s = Settings(tts_provider="elevenlabs")  # keine Keys
    assert isinstance(build_tts(s, AudioStore()), NullTTS)


def test_factory_builds_elevenlabs_with_keys():
    s = Settings(tts_provider="elevenlabs", elevenlabs_api_key="k", elevenlabs_voice_id="v")
    provider = build_tts(s, AudioStore())
    # Nicht NullTTS -> ElevenLabs aktiv
    assert not isinstance(provider, NullTTS)
