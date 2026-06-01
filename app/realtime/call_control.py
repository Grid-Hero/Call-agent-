"""Anrufsteuerung im Echtzeit-Modus (Weiterleiten / Auflegen).

Innerhalb eines Media Streams kann nicht direkt `<Dial>` verwendet werden – der
laufende Anruf wird stattdessen über die Twilio-REST-API mit neuem TwiML
umgeleitet bzw. beendet. Die (synchrone) Twilio-Bibliothek läuft in einem
Thread, um den Event-Loop nicht zu blockieren.
"""

from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from xml.sax.saxutils import escape

from app.config import Settings

logger = logging.getLogger(__name__)


class CallControl(ABC):
    @abstractmethod
    async def transfer(self, call_sid: str, number: str) -> None:
        """Stellt den laufenden Anruf an ``number`` durch."""

    @abstractmethod
    async def hangup(self, call_sid: str) -> None:
        """Beendet den laufenden Anruf."""


class TwilioCallControl(CallControl):
    def __init__(self, settings: Settings):
        self.settings = settings
        self._client = None

    @property
    def client(self):
        if self._client is None:
            from twilio.rest import Client

            self._client = Client(
                self.settings.twilio_account_sid, self.settings.twilio_auth_token
            )
        return self._client

    async def transfer(self, call_sid: str, number: str) -> None:
        caller_id = escape(self.settings.twilio_phone_number or "")
        twiml = (
            f'<Response><Dial callerId="{caller_id}">'
            f"<Number>{escape(number)}</Number></Dial></Response>"
        )
        await asyncio.to_thread(self.client.calls(call_sid).update, twiml=twiml)
        logger.info("Anruf %s an %s durchgestellt", call_sid, number)

    async def hangup(self, call_sid: str) -> None:
        await asyncio.to_thread(self.client.calls(call_sid).update, status="completed")
        logger.info("Anruf %s beendet", call_sid)
