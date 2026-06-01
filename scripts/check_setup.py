"""Prüft die in der .env hinterlegten Zugänge mit minimalen Test-Aufrufen.

Aufruf (lokal, im Projektverzeichnis):

    source .venv/bin/activate
    python scripts/check_setup.py

Das Skript gibt für jeden Dienst ✅/❌ aus und gibt KEINE Key-Werte preis.
Es prüft nur die Zugänge, die laut Konfiguration auch genutzt werden.
"""

from __future__ import annotations

import smtplib
import sys
from pathlib import Path

# Projekt-Wurzel in den Importpfad aufnehmen (Skript liegt in scripts/).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import get_settings  # noqa: E402


def _ok(label: str, detail: str = "") -> bool:
    print(f"  ✅ {label}" + (f" – {detail}" if detail else ""))
    return True


def _fail(label: str, detail: str = "") -> bool:
    print(f"  ❌ {label}" + (f" – {detail}" if detail else ""))
    return False


def _skip(label: str, detail: str = "") -> None:
    print(f"  ⬜ {label}" + (f" – {detail}" if detail else ""))


def check_anthropic(s) -> bool:
    print("Anthropic / Claude")
    if not s.anthropic_api_key:
        return _fail("ANTHROPIC_API_KEY", "fehlt in .env")
    try:
        from anthropic import Anthropic

        client = Anthropic(api_key=s.anthropic_api_key)
        client.messages.create(
            model=s.anthropic_model,
            max_tokens=1,
            messages=[{"role": "user", "content": "ping"}],
        )
        return _ok("Claude erreichbar", f"Modell {s.anthropic_model}")
    except Exception as exc:  # noqa: BLE001
        msg = str(exc).lower()
        if "credit" in msg or "billing" in msg or "balance" in msg:
            return _fail("Claude", "Guthaben zu niedrig – unter Billing aufladen")
        if "authentication" in msg or "401" in msg or "invalid x-api-key" in msg:
            return _fail("Claude", "Key ungültig")
        return _fail("Claude", str(exc)[:120])


def check_twilio(s) -> bool:
    print("Twilio")
    if not (s.twilio_account_sid and s.twilio_auth_token):
        return _fail("TWILIO_ACCOUNT_SID/AUTH_TOKEN", "fehlt in .env")
    try:
        from twilio.rest import Client

        client = Client(s.twilio_account_sid, s.twilio_auth_token)
        account = client.api.accounts(s.twilio_account_sid).fetch()
        result = _ok("Twilio-Konto", f"Status: {account.status}")
        if s.twilio_phone_number:
            numbers = client.incoming_phone_numbers.list(
                phone_number=s.twilio_phone_number, limit=1
            )
            if numbers:
                _ok("Telefonnummer gefunden", s.twilio_phone_number)
            else:
                _fail("Telefonnummer", f"{s.twilio_phone_number} nicht im Konto")
        else:
            _skip("TWILIO_PHONE_NUMBER", "nicht gesetzt")
        return result
    except Exception as exc:  # noqa: BLE001
        return _fail("Twilio", str(exc)[:120])


def check_smtp(s) -> bool:
    print("SMTP / E-Mail")
    if not s.smtp_host:
        return _fail("SMTP_HOST", "fehlt in .env")
    try:
        server = smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=10)
        if s.smtp_use_tls:
            server.starttls()
        if s.smtp_username:
            server.login(s.smtp_username, s.smtp_password)
        server.quit()
        return _ok("SMTP-Login", s.smtp_host)
    except Exception as exc:  # noqa: BLE001
        return _fail("SMTP", str(exc)[:120])


def check_elevenlabs(s) -> bool:
    print("ElevenLabs (Stimme)")
    if not s.elevenlabs_api_key:
        return _fail("ELEVENLABS_API_KEY", "fehlt, aber TTS_PROVIDER=elevenlabs")
    try:
        import httpx

        r = httpx.get(
            "https://api.elevenlabs.io/v1/user",
            headers={"xi-api-key": s.elevenlabs_api_key},
            timeout=10,
        )
        if r.status_code != 200:
            return _fail("ElevenLabs", f"HTTP {r.status_code} (Key prüfen)")
        result = _ok("ElevenLabs-Key gültig")
        if s.elevenlabs_voice_id:
            rv = httpx.get(
                f"https://api.elevenlabs.io/v1/voices/{s.elevenlabs_voice_id}",
                headers={"xi-api-key": s.elevenlabs_api_key},
                timeout=10,
            )
            if rv.status_code == 200:
                _ok("Voice-ID gefunden", s.elevenlabs_voice_id)
            else:
                _fail("Voice-ID", f"{s.elevenlabs_voice_id} nicht gefunden")
        else:
            _fail("ELEVENLABS_VOICE_ID", "nicht gesetzt")
        return result
    except Exception as exc:  # noqa: BLE001
        return _fail("ElevenLabs", str(exc)[:120])


def check_deepgram(s) -> bool:
    print("Deepgram (Echtzeit-STT)")
    if not s.deepgram_api_key:
        return _fail("DEEPGRAM_API_KEY", "fehlt, aber CONVERSATION_MODE=realtime")
    try:
        import httpx

        r = httpx.get(
            "https://api.deepgram.com/v1/projects",
            headers={"Authorization": f"Token {s.deepgram_api_key}"},
            timeout=10,
        )
        if r.status_code == 200:
            return _ok("Deepgram-Key gültig")
        return _fail("Deepgram", f"HTTP {r.status_code} (Key prüfen)")
    except Exception as exc:  # noqa: BLE001
        return _fail("Deepgram", str(exc)[:120])


def main() -> int:
    s = get_settings()
    print("=" * 50)
    print(" Call-Agent – Setup-Prüfung")
    print("=" * 50)
    print(f"Modus: CONVERSATION_MODE={s.conversation_mode}, TTS_PROVIDER={s.tts_provider}\n")

    results = [check_anthropic(s), check_twilio(s), check_smtp(s)]

    if s.tts_provider == "elevenlabs" or s.conversation_mode == "realtime":
        print()
        results.append(check_elevenlabs(s))
    if s.conversation_mode == "realtime":
        print()
        results.append(check_deepgram(s))

    print("\n" + "=" * 50)
    if all(results):
        print(" Alles bereit – du kannst einen Testanruf machen! 🎉")
        print("=" * 50)
        return 0
    print(" Es gibt offene Punkte (siehe ❌ oben). Details: docs/SETUP.md")
    print("=" * 50)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
