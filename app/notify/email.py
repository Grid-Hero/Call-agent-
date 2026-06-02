"""Versendet Gesprächszusammenfassungen per E-Mail an den Mitarbeiter.

Zwei Versandwege (EMAIL_PROVIDER):
- "smtp"  : klassischer SMTP-Versand (z.B. Brevo-SMTP, Office 365)
- "brevo" : Brevos HTTP-API (api.brevo.com) – robust auf Cloud-Hostern,
            keine Port-/STARTTLS-Probleme; benötigt nur BREVO_API_KEY.
"""

from __future__ import annotations

import logging
from email.message import EmailMessage

import aiosmtplib
import httpx

from app.config import Settings
from app.models import CallSession, CallSummary

logger = logging.getLogger(__name__)

_BREVO_API = "https://api.brevo.com/v3/smtp/email"


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


def _subject(summary: CallSummary) -> str:
    prefix = f"[{summary.urgency.upper()}] " if summary.urgency == "hoch" else ""
    return f"{prefix}Anruf: {summary.subject}"


def build_message(summary: CallSummary, session: CallSession, settings: Settings, to_addr: str) -> EmailMessage:
    """Baut die EmailMessage (SMTP-Pfad; auch ohne Versand testbar)."""
    msg = EmailMessage()
    msg["Subject"] = _subject(summary)
    msg["From"] = settings.email_from
    msg["To"] = to_addr
    if summary.callback_requested and summary.callback_number:
        msg["Reply-To"] = summary.callback_number
    msg.set_content(_render_body(summary, session))
    return msg


# --- Versandwege -------------------------------------------------------------
async def _deliver(settings: Settings, to_addr: str, subject: str, body: str) -> tuple[bool, str]:
    """Versendet eine einfache Text-E-Mail über den konfigurierten Weg."""
    provider = (settings.email_provider or "smtp").lower()
    if provider == "brevo":
        return await _deliver_brevo(settings, to_addr, subject, body)
    return await _deliver_smtp(settings, to_addr, subject, body)


async def _deliver_smtp(settings: Settings, to_addr: str, subject: str, body: str) -> tuple[bool, str]:
    if not settings.smtp_host:
        return False, "Kein SMTP_HOST konfiguriert."
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = settings.email_from
    msg["To"] = to_addr
    msg.set_content(body)
    try:
        await aiosmtplib.send(
            msg,
            hostname=settings.smtp_host,
            port=settings.smtp_port,
            username=settings.smtp_username or None,
            password=settings.smtp_password or None,
            start_tls=settings.smtp_use_tls,
            timeout=20,
        )
        return True, "gesendet (SMTP)"
    except Exception as exc:  # noqa: BLE001
        return False, f"SMTP-Fehler: {str(exc)[:200]}"


async def _deliver_brevo(settings: Settings, to_addr: str, subject: str, body: str) -> tuple[bool, str]:
    if not settings.brevo_api_key:
        return False, "Kein BREVO_API_KEY konfiguriert."
    if not settings.email_from:
        return False, "Kein EMAIL_FROM (Absender) konfiguriert."
    payload = {
        "sender": {"email": settings.email_from},
        "to": [{"email": to_addr}],
        "subject": subject,
        "textContent": body,
    }
    headers = {
        "api-key": settings.brevo_api_key,
        "content-type": "application/json",
        "accept": "application/json",
    }
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.post(_BREVO_API, headers=headers, json=payload)
        if r.status_code in (200, 201):
            return True, "gesendet (Brevo-API)"
        return False, f"Brevo-API HTTP {r.status_code}: {r.text[:200]}"
    except Exception as exc:  # noqa: BLE001
        return False, f"Brevo-API-Fehler: {str(exc)[:200]}"


# --- Öffentliche Funktionen --------------------------------------------------
async def send_summary(
    summary: CallSummary, session: CallSession, settings: Settings, to_addr: str
) -> bool:
    """Versendet die Zusammenfassung. Gibt True bei Erfolg zurück."""
    ok, detail = await _deliver(settings, to_addr, _subject(summary), _render_body(summary, session))
    if ok:
        logger.info("Zusammenfassung an %s gesendet (Anruf %s)", to_addr, session.call_sid)
    else:
        logger.error("E-Mail-Versand an %s fehlgeschlagen: %s", to_addr, detail)
    return ok


async def send_test_email(settings: Settings, to_addr: str) -> tuple[bool, str]:
    """Versendet eine Test-E-Mail und gibt (Erfolg, Meldung) zurück."""
    if not to_addr:
        return False, "Keine Empfängeradresse (EMAIL_FALLBACK_TO) gesetzt."
    body = (
        "Dies ist eine Test-E-Mail vom Call-Agent.\n\n"
        "Wenn du das liest, funktioniert der E-Mail-Versand korrekt. 🎉"
    )
    ok, detail = await _deliver(settings, to_addr, "Call-Agent – Test-E-Mail ✅", body)
    if ok:
        return True, f"Test-E-Mail an {to_addr} gesendet ({detail})."
    return False, detail
