"""Tests für die TwiML-Erzeugung des Twilio-Adapters."""

from __future__ import annotations

from app.telephony.twilio_adapter import TwilioAdapter


def test_greeting_twiml(settings):
    adapter = TwilioAdapter(settings)
    xml = adapter.greeting_response("Guten Tag!", "https://x/voice/handle", "de-DE")
    assert "<Gather" in xml
    assert 'input="speech"' in xml
    assert "Guten Tag!" in xml
    assert "de-DE" in xml


def test_transfer_twiml(settings):
    adapter = TwilioAdapter(settings)
    xml = adapter.transfer_response("Ich verbinde Sie.", "+4930111", "de-DE", "https://x/after")
    assert "<Dial" in xml
    assert "+4930111" in xml
    assert "Ich verbinde Sie." in xml


def test_hangup_twiml(settings):
    adapter = TwilioAdapter(settings)
    xml = adapter.hangup_response("Auf Wiederhören!", "de-DE")
    assert "<Hangup" in xml
    assert "Auf Wiederhören!" in xml


def test_greeting_uses_play_with_audio_url(settings):
    adapter = TwilioAdapter(settings)
    xml = adapter.greeting_response(
        "Guten Tag!", "https://x/voice/handle", "de-DE", audio_url="https://x/audio/a.mp3"
    )
    assert "<Play>https://x/audio/a.mp3</Play>" in xml
    assert "<Say" not in xml  # ElevenLabs-Audio statt Twilio-Stimme


def test_parse_incoming_and_speech(settings):
    adapter = TwilioAdapter(settings)
    form = {"CallSid": "CA1", "From": "+4915112345", "To": "+4930000", "SpeechResult": "Ich brauche Hilfe"}
    sid, caller, called = adapter.parse_incoming(form)
    assert sid == "CA1"
    assert caller == "+4915112345"
    assert adapter.parse_speech(form) == "Ich brauche Hilfe"
