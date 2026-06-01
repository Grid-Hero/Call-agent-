"""Transport-Abstraktion über die Twilio-WebSocket-Verbindung.

Trennt die Gesprächslogik (session.py) von der konkreten WebSocket-API, sodass
sie mit einem Fake-Transport testbar bleibt.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Optional

from app.realtime import protocol

logger = logging.getLogger(__name__)


class MediaTransport(ABC):
    """Bidirektionaler Audio-/Steuerkanal zum Telefonie-Anbieter."""

    stream_sid: str = ""

    @abstractmethod
    async def receive(self) -> Optional[dict]:
        """Nächste eingehende Nachricht (geparst) oder None bei Verbindungsende."""

    @abstractmethod
    async def send_audio(self, audio: bytes) -> None:
        """Sendet μ-law-Audio (Agent-Stimme) an den Anrufer."""

    @abstractmethod
    async def send_clear(self) -> None:
        """Bricht die laufende Wiedergabe ab (Barge-in)."""

    @abstractmethod
    async def send_mark(self, name: str) -> None:
        """Setzt eine Wiedergabe-Marke."""

    @abstractmethod
    async def close(self) -> None:
        """Schließt die Verbindung."""


class TwilioWebSocketTransport(MediaTransport):
    """Implementierung über eine FastAPI/Starlette-WebSocket."""

    def __init__(self, websocket) -> None:
        self.ws = websocket
        self.stream_sid = ""
        self._closed = False

    async def receive(self) -> Optional[dict]:
        try:
            raw = await self.ws.receive_text()
        except Exception:  # WebSocketDisconnect u.a.
            return None
        return protocol.parse_message(raw)

    async def send_audio(self, audio: bytes) -> None:
        if self._closed or not self.stream_sid or not audio:
            return
        await self.ws.send_text(protocol.build_media_message(self.stream_sid, audio))

    async def send_clear(self) -> None:
        if self._closed or not self.stream_sid:
            return
        await self.ws.send_text(protocol.build_clear_message(self.stream_sid))

    async def send_mark(self, name: str) -> None:
        if self._closed or not self.stream_sid:
            return
        await self.ws.send_text(protocol.build_mark_message(self.stream_sid, name))

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            await self.ws.close()
        except Exception:  # pragma: no cover - bereits geschlossen
            pass
