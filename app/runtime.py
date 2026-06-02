"""Zentraler Laufzeit-Container: bündelt die verdrahteten Komponenten.

Ermöglicht ein Live-Neuladen der Konfiguration (z.B. nach Änderungen über die
Admin-Oberfläche), ohne den Prozess neu zu starten: ``reload()`` baut Agent,
Adapter, TTS und Orchestrator anhand der aktuellen ``directory.yaml`` neu auf.
"""

from __future__ import annotations

import logging

from app.ai.agent import CallAgent
from app.config import Settings
from app.directory import load_directory
from app.orchestrator import Orchestrator, SessionStore
from app.telephony.twilio_adapter import TwilioAdapter
from app.tts.factory import build_tts
from app.tts.store import AudioStore

logger = logging.getLogger(__name__)


class Runtime:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.audio_store = AudioStore()
        self.session_store = SessionStore()
        self.reload()

    def _build_adapter(self):
        if self.settings.telephony_provider == "twilio":
            return TwilioAdapter(self.settings)
        if self.settings.telephony_provider == "asterisk":
            from app.telephony.asterisk_adapter import AsteriskAdapter

            return AsteriskAdapter(self.settings)
        raise RuntimeError(f"Unbekannter TELEPHONY_PROVIDER: {self.settings.telephony_provider}")

    def reload(self) -> None:
        """Lädt die Verzeichnis-Konfiguration neu und baut die Komponenten auf."""
        self.directory = load_directory(self.settings.directory_path)
        self.agent = CallAgent(self.settings, self.directory)
        self.adapter = self._build_adapter()
        self.tts = build_tts(self.settings, self.audio_store)
        self.orchestrator = Orchestrator(
            self.settings, self.directory, self.adapter, self.agent,
            self.session_store, self.tts,
        )
        logger.info(
            "Runtime geladen: %s (%d Abteilungen)",
            self.directory.company_name, len(self.directory.departments),
        )
