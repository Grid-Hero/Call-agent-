"""Versendet Gesprächszusammenfassungen per E-Mail (SMTP) an den Mitarbeiter."""

from __future__ import annotations

import logging
from email.message import EmailMessage

import aiosmtplib

from app.config import Settings
from app.models import CallSession, CallSummary

logger = logging.getLogger(__name__)


def _render_body(summary: CallSummary, session: CallSession) -> str:
    """Erzeugt den lesbaren E-Mail-Text."""
    callback = (
        f"Ja – Rückrufnummer: {summary.callback_number}"
        if summary.callback_requested
        else "Nicht ausdrücklich gewünscht"
    )
    started = session.started_at.strftime("%d.%m.%Y %H:%M UTC")
    return f"""Neuer Anruf wurde vom digitalen Telefonassistenten bearbeitet.

Abteilung:      {summary.department_name}
Anrufernummer:  {summary.caller_number}
Eingegangen:    {started}
Dringlichkeit:  {summary.urgency.upper()}
Rückruf:        {callback}

Anliegen:
{summary.caller_request}

Zusammenfassung:
{summary.summary}

----------------------------------------
Gesprächsverlauf (Wortlaut):
{session.transcript() or "(kein Wortlaut erfasst)"}
----------------------------------------
Diese E-Mail wurde automatisch erstellt.
"""


def build_message(summary: CallSummary, session: CallSession, settings: Settings, to_addr: str) -> EmailMessage:
    """Baut die EmailMessage (auch ohne SMTP testbar)."""
    msg = EmailMessage()
    prefix = f"[{summary.urgency.upper()}] " if summary.urgency == "hoch" else ""
    msg["Subject"] = f"{prefix}Anruf: {summary.subject}"
    msg["From"] = settings.email_from
    msg["To"] = to_addr
    if summary.callback_requested and summary.callback_number:
        msg["Reply-To"] = summary.callback_number
    msg.set_content(_render_body(summary, session))
    return msg


async def send_summary(
    summary: CallSummary, session: CallSession, settings: Settings, to_addr: str
) -> bool:
    """Versendet die Zusammenfassung. Gibt True bei Erfolg zurück."""
    if not settings.smtp_host:
        logger.warning("Kein SMTP-Host konfiguriert – E-Mail wird übersprungen.")
        return False

    message = build_message(summary, session, settings, to_addr)
    try:
        await aiosmtplib.send(
            message,
            hostname=settings.smtp_host,
            port=settings.smtp_port,
            username=settings.smtp_username or None,
            password=settings.smtp_password or None,
            start_tls=settings.smtp_use_tls,
            timeout=20,
        )
        logger.info("Zusammenfassung an %s gesendet (Anruf %s)", to_addr, session.call_sid)
        return True
    except Exception:  # pragma: no cover - Netzwerk/Server
        logger.exception("E-Mail-Versand an %s fehlgeschlagen", to_addr)
        return False
