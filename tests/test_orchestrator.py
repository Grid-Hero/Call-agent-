"""Tests für den Orchestrator mit gemocktem Claude-Agent (kein API-Aufruf)."""

from __future__ import annotations

import pytest

from app.ai.agent import CallAgent
from app.directory import load_directory
from app.models import Action, RoutingDecision, CallSummary
from app.orchestrator import Orchestrator, SessionStore
from app.telephony.twilio_adapter import TwilioAdapter


class FakeAgent(CallAgent):
    """Ersetzt die Claude-Aufrufe durch vorgegebene Antworten."""

    def __init__(self, settings, directory, decision: RoutingDecision):
        self.settings = settings
        self.directory = directory
        self._decision = decision

    async def decide(self, session, is_open):
        return self._decision

    async def summarize(self, session):
        name, *_ = self.directory.routing_target(session.department_id)
        return CallSummary(
            caller_number=session.caller_number,
            department_id=session.department_id,
            department_name=name,
            subject="Testbetreff",
            summary="Test-Zusammenfassung.",
            caller_request="Test-Anliegen.",
        )


def _orchestrator(settings, directory, decision):
    return Orchestrator(
        settings, directory, TwilioAdapter(settings),
        FakeAgent(settings, directory, decision), SessionStore(),
    )


def test_incoming_creates_session_and_greets(settings, directory):
    orch = _orchestrator(settings, directory, RoutingDecision(action=Action.CONTINUE, reply_text="..."))
    xml = orch.handle_incoming({"CallSid": "CA1", "From": "+4915100", "To": "+4930"})
    assert "<Gather" in xml
    assert orch.store.get("CA1") is not None


@pytest.mark.asyncio
async def test_transfer_flow(settings, directory):
    decision = RoutingDecision(action=Action.TRANSFER, reply_text="Ich verbinde Sie.", department_id="support")
    orch = _orchestrator(settings, directory, decision)
    orch.handle_incoming({"CallSid": "CA2", "From": "+4915100", "To": "+4930"})
    xml = await orch.handle_speech({"CallSid": "CA2", "From": "+4915100", "SpeechResult": "Mein Gerät ist defekt"})
    assert "<Dial" in xml
    assert orch.store.get("CA2").transferred is True


@pytest.mark.asyncio
async def test_message_flow_closes_session(settings, directory):
    decision = RoutingDecision(action=Action.MESSAGE, reply_text="Ich nehme das auf.", department_id="buchhaltung")
    orch = _orchestrator(settings, directory, decision)
    orch.handle_incoming({"CallSid": "CA3", "From": "+4915100", "To": "+4930"})
    xml = await orch.handle_speech({"CallSid": "CA3", "From": "+4915100", "SpeechResult": "Frage zur Rechnung"})
    assert "<Hangup" in xml
    # Nach Nachricht wird die Session beendet/entfernt.
    assert orch.store.get("CA3") is None


@pytest.mark.asyncio
async def test_transfer_disabled_falls_back_to_message(settings, directory):
    # buchhaltung hat transfer_enabled: false -> trotz TRANSFER kein Dial
    decision = RoutingDecision(action=Action.TRANSFER, reply_text="Moment.", department_id="buchhaltung")
    orch = _orchestrator(settings, directory, decision)
    orch.handle_incoming({"CallSid": "CA4", "From": "+4915100", "To": "+4930"})
    xml = await orch.handle_speech({"CallSid": "CA4", "From": "+4915100", "SpeechResult": "Rechnungsfrage"})
    assert "<Dial" not in xml
    assert "<Hangup" in xml
