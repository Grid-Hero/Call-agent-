"""Tests für die STT-Anbieterauswahl und das ElevenLabs-Event-Parsing."""

from __future__ import annotations

import json

import pytest

from app.config import Settings
from app.realtime.factory import build_stt
from app.realtime.stt import DeepgramSTT, ElevenLabsSTT, STTEventType


def test_factory_defaults_to_elevenlabs():
    assert isinstance(build_stt(Settings()), ElevenLabsSTT)


def test_factory_deepgram_when_selected():
    assert isinstance(build_stt(Settings(stt_provider="deepgram")), DeepgramSTT)


def test_stt_language_derived_from_agent_language():
    assert Settings(agent_language="de-DE").stt_language == "de"
    assert Settings(agent_language="en-US").stt_language == "en"


class _FakeWS:
    """Minimaler WebSocket-Ersatz, der vorgegebene Nachrichten liefert."""

    def __init__(self, messages):
        self._messages = [json.dumps(m) for m in messages]

    def __aiter__(self):
        async def gen():
            for m in self._messages:
                yield m
        return gen()


@pytest.mark.asyncio
async def test_elevenlabs_events_map_to_stt_events():
    stt = ElevenLabsSTT(Settings())
    stt._ws = _FakeWS(
        [
            {"message_type": "partial_transcript", "text": "Guten"},
            {"message_type": "partial_transcript", "text": "Guten Tag"},
            {"message_type": "committed_transcript", "text": "Guten Tag, ich habe eine Frage"},
        ]
    )
    events = [e async for e in stt.events()]
    types = [e.type for e in events]
    # Erstes Partial -> SPEECH_STARTED (einmalig), dann finales Transkript + Äußerungsende.
    assert types[0] == STTEventType.SPEECH_STARTED
    assert STTEventType.TRANSCRIPT in types
    assert types[-1] == STTEventType.UTTERANCE_END
    final = next(e for e in events if e.type == STTEventType.TRANSCRIPT)
    assert final.is_final is True
    assert "Frage" in final.text
