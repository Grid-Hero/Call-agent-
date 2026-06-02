"""Echtzeit-Gesprächssitzung: verbindet Media Stream, STT, Claude und TTS.

Ablauf:
  1. Twilio öffnet die WebSocket und sendet ein 'start'-Event (streamSid/callSid).
  2. Der Agent begrüßt (TTS-Stream -> Twilio).
  3. Eingehendes Audio wird an die STT weitergereicht.
  4. Bei Äußerungsende entscheidet Claude (continue/transfer/message/goodbye).
  5. Antwort wird gestreamt; spricht der Anrufer dazwischen (Barge-in), wird die
     Wiedergabe sofort gestoppt.
  6. Bei transfer/message/goodbye: ggf. durchstellen, Zusammenfassung mailen,
     Anruf beenden.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

from app.ai.agent import CallAgent
from app.config import Settings
from app.directory import Directory, is_demo_phone
from app.finalize import finish_with_message
from app.models import Action, CallSession, RoutingDecision, Speaker
from app.realtime.call_control import CallControl
from app.realtime.stt import StreamingSTT, STTEvent, STTEventType
from app.realtime.transport import MediaTransport
from app.realtime.tts_stream import StreamingTTS

logger = logging.getLogger(__name__)


class RealtimeCallSession:
    def __init__(
        self,
        settings: Settings,
        directory: Directory,
        agent: CallAgent,
        transport: MediaTransport,
        stt: StreamingSTT,
        tts: StreamingTTS,
        call_control: CallControl,
        call_log=None,
    ):
        self.settings = settings
        self.directory = directory
        self.agent = agent
        self.transport = transport
        self.stt = stt
        self.tts = tts
        self.call_control = call_control
        self.call_log = call_log

        self.call_sid: str = ""
        self.session: Optional[CallSession] = None
        self._speaking = False
        self._speak_task: Optional[asyncio.Task] = None
        self._utterance: list[str] = []
        self._done = asyncio.Event()

    @property
    def lang(self) -> str:
        return self.settings.agent_language

    # --- Lebenszyklus -------------------------------------------------------
    async def run(self) -> None:
        """Hauptschleife für die Dauer des Anrufs."""
        if not await self._await_start():
            return
        await self.stt.start()
        await self._say_and_wait(self.directory.greeting)

        pump = asyncio.create_task(self._pump_inbound())
        process = asyncio.create_task(self._process_stt())
        try:
            await self._done.wait()
        finally:
            for task in (pump, process, self._speak_task):
                if task and not task.done():
                    task.cancel()
            await self.stt.aclose()
            await self.transport.close()

    async def _await_start(self) -> bool:
        """Wartet auf das 'start'-Event und übernimmt streamSid/callSid."""
        while True:
            message = await self.transport.receive()
            if message is None:
                return False
            if message.get("event") == "start":
                start = message.get("start", {})
                self.transport.stream_sid = start.get("streamSid") or message.get("streamSid", "")
                self.call_sid = start.get("callSid", "")
                caller = start.get("customParameters", {}).get("from", "unbekannt")
                self.session = CallSession(call_sid=self.call_sid, caller_number=caller)
                logger.info("Media Stream gestartet (Call %s)", self.call_sid)
                return True

    # --- Eingehendes Audio --------------------------------------------------
    async def _pump_inbound(self) -> None:
        from app.realtime import protocol

        while not self._done.is_set():
            message = await self.transport.receive()
            if message is None or protocol.event_type(message) == "stop":
                self._done.set()
                return
            if protocol.is_inbound_media(message):
                await self.stt.send_audio(protocol.media_payload_bytes(message))

    # --- STT-Ereignisse -----------------------------------------------------
    async def _process_stt(self) -> None:
        async for event in self.stt.events():
            if self._done.is_set():
                return
            await self._on_stt_event(event)

    async def _on_stt_event(self, event: STTEvent) -> None:
        if event.type == STTEventType.SPEECH_STARTED:
            await self._barge_in()
        elif event.type == STTEventType.TRANSCRIPT and event.is_final:
            self._utterance.append(event.text)
        elif event.type == STTEventType.UTTERANCE_END:
            text = " ".join(self._utterance).strip()
            self._utterance.clear()
            if text:
                await self._handle_utterance(text)

    async def _barge_in(self) -> None:
        """Anrufer spricht, während der Agent redet -> Wiedergabe abbrechen."""
        if self._speaking and self._speak_task and not self._speak_task.done():
            self._speak_task.cancel()
            await self.transport.send_clear()
            logger.debug("Barge-in: Wiedergabe abgebrochen")

    # --- Sprechen -----------------------------------------------------------
    async def _say_and_wait(self, text: str) -> None:
        """Streamt die Agent-Stimme und wartet, bis sie fertig (oder unterbrochen) ist."""
        self._speak_task = asyncio.create_task(self._speak(text))
        try:
            await self._speak_task
        except asyncio.CancelledError:
            pass

    async def _speak(self, text: str) -> None:
        self._speaking = True
        try:
            async for chunk in self.tts.stream(text, self.lang):
                await self.transport.send_audio(chunk)
            await self.transport.send_mark("agent-done")
        finally:
            self._speaking = False

    # --- Entscheidung & Routing --------------------------------------------
    async def _handle_utterance(self, text: str) -> None:
        assert self.session is not None
        self.session.add_turn(Speaker.CALLER, text)
        is_open = self.directory.business_hours.is_open()
        decision = await self.agent.decide(self.session, is_open=is_open)
        self.session.add_turn(Speaker.AGENT, decision.reply_text)
        if decision.department_id:
            self.session.department_id = decision.department_id
        self.session.last_action = decision.action
        logger.info("Call %s -> action=%s", self.call_sid, decision.action.value)
        await self._apply(decision)

    async def _apply(self, decision: RoutingDecision) -> None:
        assert self.session is not None

        if decision.action == Action.CONTINUE:
            await self._say_and_wait(decision.reply_text)
            return

        if decision.action == Action.TRANSFER:
            _name, _email, phone, transfer_ok = self.directory.routing_target(
                self.session.department_id
            )
            if transfer_ok and phone and not is_demo_phone(phone):
                await self._say_and_wait(decision.reply_text)
                self.session.transferred = True
                await self.call_control.transfer(self.call_sid, phone)
                await finish_with_message(
                    self.agent, self.directory, self.settings, self.session,
                    transferred_note=True, call_log=self.call_log,
                )
                self._done.set()
                return
            # Durchstellen nicht möglich -> Nachricht aufnehmen.
            await self._say_and_wait(
                "Ich leite Ihr Anliegen an die zuständige Stelle weiter. "
                "Ein Mitarbeiter meldet sich bei Ihnen. Auf Wiederhören!"
            )
            await self._finalize_and_hangup()
            return

        if decision.action == Action.MESSAGE:
            await self._say_and_wait(decision.reply_text)
            await self._finalize_and_hangup()
            return

        # GOODBYE
        await self._say_and_wait(decision.reply_text)
        await self.call_control.hangup(self.call_sid)
        self._done.set()

    async def _finalize_and_hangup(self) -> None:
        assert self.session is not None
        await finish_with_message(
            self.agent, self.directory, self.settings, self.session, call_log=self.call_log
        )
        await self.call_control.hangup(self.call_sid)
        self._done.set()
