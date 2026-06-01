"""Abstrakte TTS-Schnittstelle."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional


class TTSProvider(ABC):
    @abstractmethod
    async def synthesize(self, text: str, language: str) -> Optional[str]:
        """Erzeugt Audio für ``text`` und gibt eine abrufbare URL zurück.

        Rückgabe ``None`` signalisiert dem Telefonie-Adapter, die eingebaute
        Anbieter-Stimme zu verwenden (z.B. Twilio ``<Say>``). So bleibt der
        Anruf auch bei TTS-Ausfall sprechfähig.
        """


class NullTTS(TTSProvider):
    """Kein eigenes TTS – nutzt die Stimme des Telefonie-Anbieters."""

    async def synthesize(self, text: str, language: str) -> Optional[str]:
        return None
