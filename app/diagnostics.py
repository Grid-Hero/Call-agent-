"""Live-Checks der externen Dienste für das Selbsttest-Dashboard (/admin/status).

Asynchron, mit kurzen Timeouts, damit die Statusseite zügig lädt. Gibt pro
Dienst einen Status zurück: "ok", "warn" (erreichbar, aber Hinweis) oder "fail".
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

import httpx

from app.config import Settings

logger = logging.getLogger(__name__)


@dataclass
class Check:
    name: str
    status: str  # "ok" | "warn" | "fail"
    detail: str = ""


async def check_claude(s: Settings) -> Check:
    name = "Claude (KI)"
    if not s.anthropic_api_key:
        return Check(name, "fail", "ANTHROPIC_API_KEY fehlt")
    try:
        from anthropic import AsyncAnthropic

        client = AsyncAnthropic(api_key=s.anthropic_api_key, timeout=10.0, max_retries=0)
        await client.messages.create(
            model=s.anthropic_model,
            max_tokens=1,
            messages=[{"role": "user", "content": "ping"}],
        )
        return Check(name, "ok", f"Modell {s.anthropic_model}")
    except Exception as exc:  # noqa: BLE001
        msg = str(exc).lower()
        if "overloaded" in msg or "529" in msg:
            return Check(name, "warn", "kurz überlastet – Fallback-Modell greift")
        if "not_found" in msg or "404" in msg:
            return Check(name, "fail", f"Modell ungültig: {s.anthropic_model}")
        if "authentication" in msg or "401" in msg or "x-api-key" in msg:
            return Check(name, "fail", "API-Key ungültig")
        if "credit" in msg or "balance" in msg or "billing" in msg:
            return Check(name, "fail", "Guthaben zu niedrig")
        return Check(name, "fail", str(exc)[:100])


async def check_elevenlabs(s: Settings) -> Check:
    name = "ElevenLabs (Stimme)"
    if not s.elevenlabs_api_key:
        return Check(name, "fail", "ELEVENLABS_API_KEY fehlt")
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.get(
                "https://api.elevenlabs.io/v1/user",
                headers={"xi-api-key": s.elevenlabs_api_key},
            )
        if r.status_code != 200:
            return Check(name, "fail", f"HTTP {r.status_code} (Key prüfen)")
        if s.elevenlabs_voice_id:
            async with httpx.AsyncClient(timeout=10) as c:
                rv = await c.get(
                    f"https://api.elevenlabs.io/v1/voices/{s.elevenlabs_voice_id}",
                    headers={"xi-api-key": s.elevenlabs_api_key},
                )
            if rv.status_code != 200:
                return Check(name, "warn", "Key ok, aber Voice-ID nicht gefunden")
        return Check(name, "ok", "Key & Stimme gültig")
    except Exception as exc:  # noqa: BLE001
        return Check(name, "fail", str(exc)[:100])


async def check_smtp(s: Settings) -> Check:
    name = "E-Mail (SMTP)"
    if not s.smtp_host:
        return Check(name, "fail", "SMTP_HOST fehlt")
    try:
        import aiosmtplib

        smtp = aiosmtplib.SMTP(
            hostname=s.smtp_host, port=s.smtp_port, start_tls=s.smtp_use_tls, timeout=15
        )
        await smtp.connect()
        if s.smtp_username:
            await smtp.login(s.smtp_username, s.smtp_password)
        await smtp.quit()
        return Check(name, "ok", s.smtp_host)
    except Exception as exc:  # noqa: BLE001
        return Check(name, "fail", str(exc)[:120])


async def check_twilio(s: Settings) -> Check:
    name = "Telefonie (Twilio)"
    if not (s.twilio_account_sid and s.twilio_auth_token):
        return Check(name, "fail", "Zugangsdaten fehlen")

    def _fetch() -> str:
        from twilio.rest import Client

        client = Client(s.twilio_account_sid, s.twilio_auth_token)
        return client.api.accounts(s.twilio_account_sid).fetch().status

    try:
        account_status = await asyncio.to_thread(_fetch)
        return Check(name, "ok", f"Konto: {account_status}")
    except Exception as exc:  # noqa: BLE001
        return Check(name, "fail", str(exc)[:120])


def check_directory(directory) -> Check:
    """Prüft, ob noch Demo-/Platzhalterdaten im Verzeichnis stehen."""
    name = "Konfiguration (Abteilungen)"
    problems = []
    demo_emails = [
        d.name for d in directory.departments if d.email.endswith("@example.com")
    ]
    if directory.fallback.email.endswith("@example.com"):
        demo_emails.append(directory.fallback.department_name)
    demo_phones = [
        d.name
        for d in directory.departments
        if d.phone.startswith(("+49301111", "+49302222", "+49303333", "+49304444", "+49300000"))
    ]
    no_email = [d.name for d in directory.departments if not d.email]

    if demo_emails:
        problems.append("Demo-E-Mails (@example.com): " + ", ".join(demo_emails))
    if demo_phones:
        problems.append("Demo-Telefonnummern: " + ", ".join(demo_phones))
    if no_email:
        problems.append("ohne E-Mail: " + ", ".join(no_email))
    if not directory.departments:
        return Check(name, "fail", "keine Abteilungen angelegt")

    if problems:
        return Check(name, "warn", "; ".join(problems) + " – über /admin echte Daten eintragen")
    return Check(name, "ok", f"{len(directory.departments)} Abteilungen, echte Daten")


async def run_checks(s: Settings, directory=None) -> list[Check]:
    """Führt alle relevanten Checks parallel aus."""
    service_checks = [check_claude(s), check_twilio(s), check_smtp(s)]
    if s.tts_provider == "elevenlabs" or s.conversation_mode == "realtime":
        service_checks.append(check_elevenlabs(s))
    results = list(await asyncio.gather(*service_checks))
    if directory is not None:
        results.append(check_directory(directory))
    return results
