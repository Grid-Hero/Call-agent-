"""Tests der Echtzeit-Gesprächslogik mit Fakes (kein Netzwerk, kein Audio)."""

from __future__ import annotations

import pytest

from app.models import Action, CallSession, CallSummary, RoutingDecision, Speaker
from app.realtime.call_control import CallControl
from app.realtime.session import RealtimeCallSession
from app.realtime.stt import StreamingSTT, STTEvent, STTEventType
from app.realtime.transport import MediaTransport
from app.realtime.tts_stream import StreamingTTS


class FakeTransport(MediaTransport):
    def __init__(self):
        self.stream_sid = "MZ1"
        self.audio_chunks: list[bytes] = []
        self.cleared = 0
        self.marks: list[str] = []
        self.closed = False

    async def receive(self):
        return None

    async def send_audio(self, audio):
        self.audio_chunks.append(audio)

    async def send_clear(self):
        self.cleared += 1

    async def send_mark(self, name):
        self.marks.append(name)

    async def close(self):
        self.closed = True


class FakeTTS(StreamingTTS):
    def __init__(self, chunks=None):
        self.chunks = chunks or [b"aa", b"bb", b"cc"]

    async def stream(self, text, language):
        for c in self.chunks:
            yield c


class FakeCallControl(CallControl):
    def __init__(self):
        self.transferred_to = None
        self.hung_up = False

    async def transfer(self, call_sid, number):
        self.transferred_to = number

    async def hangup(self, call_sid):
        self.hung_up = True


class FakeSTT(StreamingSTT):
    async def start(self):
        pass

    async def send_audio(self, audio):
        pass

    async def events(self):
        if False:
            yield  # pragma: no cover

    async def aclose(self):
        pass


class FakeAgent:
    def __init__(self, settings, directory, decision):
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
            subject="S", summary="Z", caller_request="A",
        )


def _session(settings, directory, decision):
    s = RealtimeCallSession(
        settings, directory,
        FakeAgent(settings, directory, decision),
        FakeTransport(), FakeSTT(), FakeTTS(), FakeCallControl(),
    )
    s.call_sid = "CA1"
    s.session = CallSession(call_sid="CA1", caller_number="+4915100")
    return s


@pytest.mark.asyncio
async def test_speak_streams_audio_and_mark(settings, directory):
    s = _session(settings, directory, RoutingDecision(action=Action.CONTINUE, reply_text="Hallo"))
    await s._say_and_wait("Hallo")
    assert s.transport.audio_chunks == [b"aa", b"bb", b"cc"]
    assert s.transport.marks == ["agent-done"]
    assert s._speaking is False


@pytest.mark.asyncio
async def test_continue_does_not_hang_up(settings, directory):
    s = _session(settings, directory, RoutingDecision(action=Action.CONTINUE, reply_text="Worum geht es?"))
    await s._handle_utterance("Hallo")
    assert s.call_control.hung_up is False
    assert s._done.is_set() is False
    # Agent-Antwort wurde dem Verlauf hinzugefügt.
    assert any(t.speaker == Speaker.AGENT for t in s.session.turns)


@pytest.mark.asyncio
async def test_transfer_routes_and_finishes(settings, directory):
    directory.get("support").phone = "+4915123456789"  # echte Nummer
    decision = RoutingDecision(action=Action.TRANSFER, reply_text="Ich verbinde Sie.", department_id="support")
    s = _session(settings, directory, decision)
    await s._handle_utterance("Mein Gerät ist defekt")
    # support hat eine echte Telefonnummer und transfer_enabled -> Durchstellen
    assert s.call_control.transferred_to == "+4915123456789"
    assert s.session.transferred is True
    assert s._done.is_set() is True


@pytest.mark.asyncio
async def test_transfer_disabled_falls_back_to_message(settings, directory):
    decision = RoutingDecision(action=Action.TRANSFER, reply_text="Moment.", department_id="buchhaltung")
    s = _session(settings, directory, decision)
    await s._handle_utterance("Frage zur Rechnung")
    # buchhaltung: transfer_enabled=false -> nicht durchstellen, sondern auflegen
    assert s.call_control.transferred_to is None
    assert s.call_control.hung_up is True
    assert s._done.is_set() is True


@pytest.mark.asyncio
async def test_message_finalizes_and_hangs_up(settings, directory):
    decision = RoutingDecision(action=Action.MESSAGE, reply_text="Ich nehme das auf.", department_id="personal")
    s = _session(settings, directory, decision)
    await s._handle_utterance("Ich möchte mich bewerben")
    assert s.call_control.hung_up is True
    assert s._done.is_set() is True


@pytest.mark.asyncio
async def test_barge_in_clears_playback(settings, directory):
    s = _session(settings, directory, RoutingDecision(action=Action.CONTINUE, reply_text="x"))

    # Simuliere laufende Wiedergabe.
    import asyncio

    async def long_speak():
        s._speaking = True
        try:
            await asyncio.sleep(10)
        finally:
            s._speaking = False

    s._speak_task = asyncio.create_task(long_speak())
    await asyncio.sleep(0)  # Task starten lassen
    await s._barge_in()
    # Cancellation einen Loop-Durchlauf abschließen lassen.
    with pytest.raises(asyncio.CancelledError):
        await s._speak_task
    assert s.transport.cleared == 1
    assert s._speak_task.cancelled()


@pytest.mark.asyncio
async def test_utterance_accumulation_via_events(settings, directory):
    s = _session(settings, directory, RoutingDecision(action=Action.CONTINUE, reply_text="ok"))
    await s._on_stt_event(STTEvent(STTEventType.TRANSCRIPT, text="Guten", is_final=True))
    await s._on_stt_event(STTEvent(STTEventType.TRANSCRIPT, text="Tag", is_final=True))
    assert s._utterance == ["Guten", "Tag"]
    await s._on_stt_event(STTEvent(STTEventType.UTTERANCE_END))
    # Nach Äußerungsende ist der Puffer geleert und der Anrufer-Turn erfasst.
    assert s._utterance == []
    assert s.session.turns[0].text == "Guten Tag"
