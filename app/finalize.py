"""Gemeinsamer Abschluss eines Anrufs: Zusammenfassung erzeugen und mailen.

Wird sowohl vom Gather-Orchestrator (app/orchestrator.py) als auch vom
Echtzeit-Modus (app/realtime) genutzt, damit die Logik nicht doppelt existiert.
"""

from __future__ import annotations

import logging

from app.ai.agent import CallAgent
from app.config import Settings
from app.directory import Directory, is_demo_email
from app.models import CallSession
from app.notify.email import send_summary

logger = logging.getLogger(__name__)


async def finish_with_message(
    agent: CallAgent,
    directory: Directory,
    settings: Settings,
    session: CallSession,
    transferred_note: bool = False,
) -> None:
    """Erzeugt die Zusammenfassung und sendet sie an die zuständige Abteilung."""
    summary = await agent.summarize(session)
    _name, email, _phone, _ = directory.routing_target(session.department_id)
    # Demo-/Platzhalter-Adressen (@example.com) nicht verwenden – dann lieber an
    # die echte Fallback-Inbox, damit Zusammenfassungen wirklich ankommen.
    to_addr = settings.email_fallback_to if is_demo_email(email) else email
    if not to_addr:
        to_addr = settings.email_fallback_to
    if transferred_note:
        summary.subject = f"[durchgestellt] {summary.subject}"
    await send_summary(summary, session, settings, to_addr)
