"""Abstrakte Telefonie-Schnittstelle.

Die Geschäftslogik (Routing via Claude, E-Mail) ist anbieterunabhängig. Jeder
Adapter (Twilio, Asterisk/Telekom-SIP, ...) übersetzt zwischen den HTTP-/Audio-
Ereignissen des Anbieters und diesen generischen Operationen.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.models import RoutingDecision


class TelephonyAdapter(ABC):
    """Erzeugt anbieterspezifische Steuerungsanweisungen für einen Anruf."""

    @abstractmethod
    def greeting_response(self, greeting_text: str, gather_action_url: str, language: str) -> str:
        """Antwort zu Gesprächsbeginn: Begrüßung + erste Spracherfassung."""

    @abstractmethod
    def continue_response(self, reply_text: str, gather_action_url: str, language: str) -> str:
        """Agent antwortet und hört erneut zu (Rückfrage)."""

    @abstractmethod
    def transfer_response(self, reply_text: str, target_number: str, language: str, status_callback_url: str) -> str:
        """Agent stellt an die Zielnummer durch."""

    @abstractmethod
    def hangup_response(self, reply_text: str, language: str) -> str:
        """Agent verabschiedet sich und legt auf."""

    @abstractmethod
    def parse_incoming(self, form: dict) -> tuple[str, str, str]:
        """Aus eingehender Anfrage: (call_sid, caller_number, called_number)."""

    @abstractmethod
    def parse_speech(self, form: dict) -> str:
        """Erkannten Sprachtext aus der Anfrage extrahieren."""
