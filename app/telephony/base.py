"""Abstrakte Telefonie-Schnittstelle.

Die Geschäftslogik (Routing via Claude, E-Mail) ist anbieterunabhängig. Jeder
Adapter (Twilio, Asterisk/Telekom-SIP, ...) übersetzt zwischen den HTTP-/Audio-
Ereignissen des Anbieters und diesen generischen Operationen.

``audio_url`` (optional): Wenn ein eigener TTS-Anbieter (z.B. ElevenLabs) das
Audio bereits erzeugt hat, wird diese URL abgespielt; sonst spricht die
eingebaute Anbieter-Stimme den ``text``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional


class TelephonyAdapter(ABC):
    """Erzeugt anbieterspezifische Steuerungsanweisungen für einen Anruf."""

    @abstractmethod
    def greeting_response(
        self, greeting_text: str, gather_action_url: str, language: str, audio_url: Optional[str] = None
    ) -> str:
        """Antwort zu Gesprächsbeginn: Begrüßung + erste Spracherfassung."""

    @abstractmethod
    def continue_response(
        self, reply_text: str, gather_action_url: str, language: str, audio_url: Optional[str] = None
    ) -> str:
        """Agent antwortet und hört erneut zu (Rückfrage)."""

    @abstractmethod
    def transfer_response(
        self,
        reply_text: str,
        target_number: str,
        language: str,
        status_callback_url: str,
        audio_url: Optional[str] = None,
    ) -> str:
        """Agent stellt an die Zielnummer durch."""

    @abstractmethod
    def hangup_response(self, reply_text: str, language: str, audio_url: Optional[str] = None) -> str:
        """Agent verabschiedet sich und legt auf."""

    @abstractmethod
    def parse_incoming(self, form: dict) -> tuple[str, str, str]:
        """Aus eingehender Anfrage: (call_sid, caller_number, called_number)."""

    @abstractmethod
    def parse_speech(self, form: dict) -> str:
        """Erkannten Sprachtext aus der Anfrage extrahieren."""
