"""Kurzlebiger Zwischenspeicher für synthetisiertes Audio.

ElevenLabs liefert Audio-Bytes; Twilio kann aber nur URLs abspielen. Daher legen
wir das Audio unter einem Zufalls-Token ab und liefern es über die Route
``/audio/{token}.mp3`` aus. Einträge verfallen nach kurzer Zeit (TTL), da Twilio
sie nur einmal kurz nach Erzeugung abruft.

Für mehrere App-Instanzen durch einen geteilten Speicher (Redis/S3) ersetzen –
siehe README, Abschnitt 'Persistenz'.
"""

from __future__ import annotations

import time
import uuid
from typing import Optional


class AudioStore:
    def __init__(self, ttl_seconds: int = 300, max_items: int = 200) -> None:
        self.ttl_seconds = ttl_seconds
        self.max_items = max_items
        # token -> (data, content_type, expires_at)
        self._items: dict[str, tuple[bytes, str, float]] = {}

    def put(self, data: bytes, content_type: str = "audio/mpeg") -> str:
        self._evict()
        token = uuid.uuid4().hex
        self._items[token] = (data, content_type, time.monotonic() + self.ttl_seconds)
        return token

    def get(self, token: str) -> Optional[tuple[bytes, str]]:
        item = self._items.get(token)
        if item is None:
            return None
        data, content_type, expires_at = item
        if time.monotonic() > expires_at:
            self._items.pop(token, None)
            return None
        return data, content_type

    def _evict(self) -> None:
        """Entfernt abgelaufene Einträge und begrenzt die Gesamtzahl."""
        now = time.monotonic()
        expired = [t for t, (_, _, exp) in self._items.items() if now > exp]
        for t in expired:
            self._items.pop(t, None)
        if len(self._items) > self.max_items:
            # Älteste (kleinste expires_at) zuerst entfernen.
            for t, _ in sorted(self._items.items(), key=lambda kv: kv[1][2])[
                : len(self._items) - self.max_items
            ]:
                self._items.pop(t, None)
