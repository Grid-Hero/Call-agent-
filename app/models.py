"""Domänenmodelle für Gespräche und Routing-Entscheidungen."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class Speaker(str, Enum):
    """Wer hat eine Äußerung gemacht?"""

    CALLER = "caller"   # Anrufer
    AGENT = "agent"     # KI-Agent


class Turn(BaseModel):
    """Eine einzelne Äußerung im Gespräch."""

    speaker: Speaker
    text: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class Action(str, Enum):
    """Mögliche Entscheidungen des Agents nach einer Anrufer-Äußerung."""

    CONTINUE = "continue"   # Rückfrage stellen, weiter zuhören
    TRANSFER = "transfer"   # An Abteilung/Mitarbeiter durchstellen
    MESSAGE = "message"     # Nachricht aufnehmen + Zusammenfassung per Mail
    GOODBYE = "goodbye"     # Gespräch beenden (kein Anliegen / Spam)


class RoutingDecision(BaseModel):
    """Strukturierte Entscheidung von Claude, wie es weitergeht."""

    action: Action
    # Antworttext, den der Agent dem Anrufer vorliest.
    reply_text: str
    # ID der zugeordneten Abteilung (aus directory.yaml), falls bekannt.
    department_id: Optional[str] = None
    # Kurze Begründung (intern, für Logs).
    reasoning: str = ""


class CallSummary(BaseModel):
    """Vom Agent erzeugte Zusammenfassung für den Mitarbeiter."""

    caller_number: str
    department_id: Optional[str]
    department_name: str
    subject: str
    summary: str
    caller_request: str
    callback_requested: bool = False
    callback_number: Optional[str] = None
    urgency: str = "normal"   # niedrig | normal | hoch


class CallSession(BaseModel):
    """Hält den Zustand eines laufenden Anrufs."""

    call_sid: str
    caller_number: str
    called_number: str = ""
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    turns: list[Turn] = Field(default_factory=list)
    department_id: Optional[str] = None
    last_action: Optional[Action] = None
    transferred: bool = False

    def add_turn(self, speaker: Speaker, text: str) -> None:
        if text and text.strip():
            self.turns.append(Turn(speaker=speaker, text=text.strip()))

    def transcript(self) -> str:
        """Lesbares Gesprächsprotokoll."""
        lines = []
        for turn in self.turns:
            who = "Anrufer" if turn.speaker == Speaker.CALLER else "Agent"
            lines.append(f"{who}: {turn.text}")
        return "\n".join(lines)
