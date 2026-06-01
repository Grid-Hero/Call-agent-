"""Tests für die Auflösung der öffentlichen Basis-URL (lokal vs. Render)."""

from __future__ import annotations

from app.config import Settings
from scripts.check_setup import should_check_deepgram


def test_explicit_base_url_wins():
    s = Settings(app_base_url="https://meine-app.example.com")
    assert s.effective_base_url == "https://meine-app.example.com"
    assert s.websocket_base_url == "wss://meine-app.example.com"


def test_render_url_fallback(monkeypatch):
    monkeypatch.setenv("RENDER_EXTERNAL_URL", "https://call-agent-xyz.onrender.com")
    s = Settings(app_base_url="http://localhost:8000")  # Default -> Fallback greift
    assert s.effective_base_url == "https://call-agent-xyz.onrender.com"
    assert s.websocket_base_url == "wss://call-agent-xyz.onrender.com"


def test_localhost_used_when_no_render(monkeypatch):
    monkeypatch.delenv("RENDER_EXTERNAL_URL", raising=False)
    s = Settings(app_base_url="http://localhost:8000")
    assert s.effective_base_url == "http://localhost:8000"


def test_deepgram_check_only_when_selected():
    assert not should_check_deepgram(
        Settings(conversation_mode="realtime", stt_provider="elevenlabs")
    )
    assert should_check_deepgram(
        Settings(conversation_mode="realtime", stt_provider="deepgram")
    )
