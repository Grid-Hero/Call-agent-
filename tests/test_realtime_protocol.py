"""Tests für das Twilio-Media-Streams-Protokoll (reine Funktionen)."""

from __future__ import annotations

import base64
import json

from app.realtime import protocol


def test_build_and_parse_media_roundtrip():
    audio = b"\x01\x02\x03\xff"
    raw = protocol.build_media_message("MZ123", audio)
    msg = protocol.parse_message(raw)
    assert msg["event"] == "media"
    assert msg["streamSid"] == "MZ123"
    assert protocol.media_payload_bytes(msg) == audio


def test_is_inbound_media():
    inbound = {"event": "media", "media": {"track": "inbound", "payload": ""}}
    outbound = {"event": "media", "media": {"track": "outbound", "payload": ""}}
    start = {"event": "start"}
    assert protocol.is_inbound_media(inbound) is True
    assert protocol.is_inbound_media(outbound) is False
    assert protocol.is_inbound_media(start) is False


def test_clear_and_mark_messages():
    clear = json.loads(protocol.build_clear_message("MZ1"))
    assert clear == {"event": "clear", "streamSid": "MZ1"}
    mark = json.loads(protocol.build_mark_message("MZ1", "done"))
    assert mark["event"] == "mark"
    assert mark["mark"]["name"] == "done"


def test_media_payload_is_base64():
    audio = b"hello-mulaw"
    raw = protocol.build_media_message("S", audio)
    payload = json.loads(raw)["media"]["payload"]
    assert base64.b64decode(payload) == audio
