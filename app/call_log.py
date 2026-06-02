"""In-Memory-Protokoll der letzten Anrufe/Zusammenfassungen.

Macht die Gesprächszusammenfassungen direkt in der Admin-Oberfläche sichtbar –
unabhängig davon, ob der E-Mail-Versand schon funktioniert. So geht keine
Anrufinfo verloren, selbst wenn SMTP gerade klemmt.

Hinweis: bewusst flüchtig (deque). Für dauerhafte Historie später durch eine
Datenbank/Tabelle ersetzen (z.B. Supabase) – siehe README, Roadmap.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone

from app.models import CallSession, CallSummary


@dataclass
class CallRecord:
    time: datetime
    caller: str
    department: str
    subject: str
    summary: str
    request: str
    urgency: str
    transferred: bool
    emailed: bool


class CallLog:
    def __init__(self, maxlen: int = 50) -> None:
        self._items: deque[CallRecord] = deque(maxlen=maxlen)

    def add(self, summary: CallSummary, session: CallSession, emailed: bool) -> None:
        self._items.appendleft(
            CallRecord(
                time=datetime.now(timezone.utc),
                caller=summary.caller_number,
                department=summary.department_name,
                subject=summary.subject,
                summary=summary.summary,
                request=summary.caller_request,
                urgency=summary.urgency,
                transferred=session.transferred,
                emailed=emailed,
            )
        )

    def recent(self) -> list[CallRecord]:
        return list(self._items)
