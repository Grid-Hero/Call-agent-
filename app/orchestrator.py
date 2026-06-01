"""Verbindet Telefonie, Claude-Agent und E-Mail zu einem Anruf-Ablauf.

Anbieterunabhängig: Die Webhook-Routen reichen die geparsten Daten hierher,
der Orchestrator entscheidet, ruft Claude, versendet E-Mails und liefert den
nächsten Telefonie-Befehl (z.B. TwiML) zurück.
"""

from __future__ import annotations

import logging

from typing import Optional

from app.ai.agent import CallAgent
from app.config import Settings
from app.directory import Directory
from app.finalize import finish_with_message
from app.models import Action, CallSession, RoutingDecision, Speaker
from app.telephony.base import TelephonyAdapter
from app.tts.base import NullTTS, TTSProvider

logger = logging.getLogger(__name__)


class SessionStore:
    """Einfacher In-Memory-Speicher für laufende Anrufe.

    Für Produktion / horizontale Skalierung durch Redis oder Supabase ersetzen
    (siehe README, Abschnitt 'Persistenz').
    """

    def __init__(self) -> None:
        self._sessions: dict[str, CallSession] = {}

    def get(self, call_sid: str) -> CallSession | None:
        return self._sessions.get(call_sid)

    def put(self, session: CallSession) -> None:
        self._sessions[session.call_sid] = session

    def pop(self, call_sid: str) -> CallSession | None:
        return self._sessions.pop(call_sid, None)


class Orchestrator:
    def __init__(
        self,
        settings: Settings,
        directory: Directory,
        adapter: TelephonyAdapter,
        agent: CallAgent,
        store: SessionStore | None = None,
        tts: TTSProvider | None = None,
    ):
        self.settings = settings
        self.directory = directory
        self.adapter = adapter
        self.agent = agent
        self.store = store or SessionStore()
        self.tts = tts or NullTTS()

    # --- URLs für Webhook-Callbacks -----------------------------------------
    def _url(self, path: str) -> str:
        return f"{self.settings.effective_base_url}{path}"

    async def _voice(self, text: str) -> Optional[str]:
        """Synthetisiert den Text via TTS-Anbieter; None => Anbieter-Stimme."""
        return await self.tts.synthesize(text, self.settings.agent_language)

    # --- Ablauf -------------------------------------------------------------
    async def handle_incoming(self, form: dict) -> str:
        """Neuer Anruf: Session anlegen, begrüßen, zuhören."""
        call_sid, caller, called = self.adapter.parse_incoming(form)
        session = CallSession(call_sid=call_sid, caller_number=caller, called_number=called)
        self.store.put(session)
        logger.info("Eingehender Anruf %s von %s", call_sid, caller)
        audio = await self._voice(self.directory.greeting)
        return self.adapter.greeting_response(
            self.directory.greeting, self._url("/voice/handle"), self.settings.agent_language, audio
        )

    async def handle_speech(self, form: dict) -> str:
        """Anrufer hat gesprochen: Claude entscheidet über das weitere Vorgehen."""
        call_sid, caller, _ = self.adapter.parse_incoming(form)
        session = self.store.get(call_sid)
        if session is None:
            session = CallSession(call_sid=call_sid, caller_number=caller)
            self.store.put(session)

        speech = self.adapter.parse_speech(form)
        session.add_turn(Speaker.CALLER, speech)

        is_open = self.directory.business_hours.is_open()
        decision = await self.agent.decide(session, is_open=is_open)
        session.add_turn(Speaker.AGENT, decision.reply_text)
        if decision.department_id:
            session.department_id = decision.department_id
        session.last_action = decision.action
        self.store.put(session)

        logger.info(
            "Anruf %s -> action=%s dept=%s",
            call_sid, decision.action.value, decision.department_id,
        )
        return await self._apply_decision(session, decision)

    async def _apply_decision(self, session: CallSession, decision: RoutingDecision) -> str:
        lang = self.settings.agent_language

        if decision.action == Action.CONTINUE:
            audio = await self._voice(decision.reply_text)
            return self.adapter.continue_response(
                decision.reply_text, self._url("/voice/handle"), lang, audio
            )

        if decision.action == Action.TRANSFER:
            name, _email, phone, transfer_ok = self.directory.routing_target(session.department_id)
            if transfer_ok and phone:
                session.transferred = True
                self.store.put(session)
                audio = await self._voice(decision.reply_text)
                return self.adapter.transfer_response(
                    decision.reply_text, phone, lang, self._url("/voice/after-transfer"), audio
                )
            # Durchstellen nicht erlaubt/möglich -> Nachricht aufnehmen.
            logger.info("Transfer für %s nicht möglich, weiche auf Nachricht aus", name)
            await self._finish_with_message(session)
            text = (
                "Ich leite Ihr Anliegen an die zuständige Stelle weiter. "
                "Ein Mitarbeiter meldet sich bei Ihnen. Auf Wiederhören!"
            )
            return self.adapter.hangup_response(text, lang, await self._voice(text))

        if decision.action == Action.MESSAGE:
            await self._finish_with_message(session)
            return self.adapter.hangup_response(
                decision.reply_text, lang, await self._voice(decision.reply_text)
            )

        # GOODBYE
        return self.adapter.hangup_response(
            decision.reply_text, lang, await self._voice(decision.reply_text)
        )

    async def handle_after_transfer(self, form: dict) -> str:
        """Nach Weiterleitung: Zusammenfassung als Protokoll per Mail senden."""
        call_sid, _, _ = self.adapter.parse_incoming(form)
        session = self.store.get(call_sid)
        if session:
            await self._finish_with_message(session, transferred_note=True)
        text = "Vielen Dank für Ihren Anruf. Auf Wiederhören!"
        return self.adapter.hangup_response(text, self.settings.agent_language, await self._voice(text))

    async def _finish_with_message(self, session: CallSession, transferred_note: bool = False) -> None:
        """Zusammenfassung erzeugen, mailen und Session beenden."""
        await finish_with_message(self.agent, self.directory, self.settings, session, transferred_note)
        self.store.pop(session.call_sid)
