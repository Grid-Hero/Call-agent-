"""Twilio Media Streams – Nachrichtenprotokoll (reine, testbare Funktionen).

Twilio sendet/empfängt JSON-Textframes über die WebSocket-Verbindung. Audio ist
base64-kodiertes μ-law (PCMU) bei 8 kHz, mono, in 20-ms-Frames.

Referenz: https://www.twilio.com/docs/voice/media-streams/websocket-messages
"""

from __future__ import annotations

import base64
import json

INBOUND_TRACK = "inbound"


def parse_message(raw: str) -> dict:
    """Parst einen eingehenden Twilio-WebSocket-Textframe."""
    return json.loads(raw)


def event_type(message: dict) -> str:
    """Twilio-Event: connected | start | media | stop | mark | dtmf."""
    return message.get("event", "")


def is_inbound_media(message: dict) -> bool:
    """True, wenn die Nachricht Audio vom Anrufer (inbound track) enthält."""
    return (
        message.get("event") == "media"
        and message.get("media", {}).get("track", INBOUND_TRACK) == INBOUND_TRACK
    )


def media_payload_bytes(message: dict) -> bytes:
    """Dekodiert die μ-law-Audiodaten aus einer media-Nachricht."""
    payload = message.get("media", {}).get("payload", "")
    return base64.b64decode(payload) if payload else b""


def build_media_message(stream_sid: str, audio: bytes) -> str:
    """Baut eine ausgehende media-Nachricht (Agent-Audio an den Anrufer)."""
    return json.dumps(
        {
            "event": "media",
            "streamSid": stream_sid,
            "media": {"payload": base64.b64encode(audio).decode("ascii")},
        }
    )


def build_clear_message(stream_sid: str) -> str:
    """Leert Twilios Audiopuffer (Barge-in: laufende Wiedergabe abbrechen)."""
    return json.dumps({"event": "clear", "streamSid": stream_sid})


def build_mark_message(stream_sid: str, name: str) -> str:
    """Setzt eine Marke; Twilio meldet sie zurück, wenn die Wiedergabe sie erreicht."""
    return json.dumps({"event": "mark", "streamSid": stream_sid, "mark": {"name": name}})
