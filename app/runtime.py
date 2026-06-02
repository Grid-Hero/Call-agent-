"""Zentraler Laufzeit-Container: bündelt die verdrahteten Komponenten.

Ermöglicht ein Live-Neuladen der Konfiguration (z.B. nach Änderungen über die
Admin-Oberfläche), ohne den Prozess neu zu starten: ``apply_directory()`` baut
Agent, Adapter, TTS und Orchestrator neu auf. Die Konfiguration wird über einen
``DirectoryStore`` geladen/gespeichert (lokale Datei oder GitHub).
"""

from __future__ import annotations

import logging

from app.ai.agent import CallAgent
from app.call_log import CallLog
from app.config import Settings
from app.directory import Directory, directory_to_yaml, parse_directory_yaml
from app.orchestrator import Orchestrator, SessionStore
from app.storage import build_store
from app.telephony.twilio_adapter import TwilioAdapter
from app.tts.factory import build_tts
from app.tts.store import AudioStore

logger = logging.getLogger(__name__)


class Runtime:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.audio_store = AudioStore()
        self.session_store = SessionStore()
        self.call_log = CallLog()
        self.store = build_store(settings)
        self.reload()

    def _build_adapter(self):
        if self.settings.telephony_provider == "twilio":
            return TwilioAdapter(self.settings)
        if self.settings.telephony_provider == "asterisk":
            from app.telephony.asterisk_adapter import AsteriskAdapter

            return AsteriskAdapter(self.settings)
        raise RuntimeError(f"Unbekannter TELEPHONY_PROVIDER: {self.settings.telephony_provider}")

    def reload(self) -> None:
        """Lädt die Konfiguration aus dem Store und baut die Komponenten neu auf."""
        self.apply_directory(parse_directory_yaml(self.store.load()))

    def apply_directory(self, directory: Directory) -> None:
        """Übernimmt ein Directory live (ohne erneutes Laden aus dem Store)."""
        self.directory = directory
        self.agent = CallAgent(self.settings, self.directory)
        self.adapter = self._build_adapter()
        self.tts = build_tts(self.settings, self.audio_store)
        self.orchestrator = Orchestrator(
            self.settings, self.directory, self.adapter, self.agent,
            self.session_store, self.tts, self.call_log,
        )
        logger.info(
            "Runtime geladen: %s (%d Abteilungen)",
            self.directory.company_name, len(self.directory.departments),
        )

    def save_directory(self, directory: Directory) -> None:
        """Übernimmt das Directory sofort live und speichert es dauerhaft.

        Reihenfolge: erst live anwenden (greift sofort, auch wenn die
        Persistierung scheitert), dann in den Store schreiben. Wirft bei einem
        Persistierungsfehler weiter – der Aufrufer kann das anzeigen.
        Achtung: store.save kann blockieren (HTTP zu GitHub) – aus async-Kontext
        via asyncio.to_thread aufrufen.
        """
        self.apply_directory(directory)
        self.store.save(directory_to_yaml(directory))
