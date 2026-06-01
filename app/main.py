"""FastAPI-Anwendung: empfängt Telefonie-Webhooks und steuert den Anruf."""

from __future__ import annotations

import logging

from fastapi import FastAPI, Form, Request, Response
from fastapi.responses import JSONResponse, PlainTextResponse

from app.ai.agent import CallAgent
from app.config import get_settings
from app.directory import get_directory
from app.orchestrator import Orchestrator, SessionStore
from app.telephony.twilio_adapter import TwilioAdapter

settings = get_settings()
logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))
logger = logging.getLogger("call-agent")

app = FastAPI(title="Call-Agent", version="0.1.0")

# --- Komponenten verdrahten --------------------------------------------------
directory = get_directory(settings.directory_path)
agent = CallAgent(settings, directory)

if settings.telephony_provider == "twilio":
    adapter = TwilioAdapter(settings)
elif settings.telephony_provider == "asterisk":
    from app.telephony.asterisk_adapter import AsteriskAdapter

    adapter = AsteriskAdapter(settings)
else:  # pragma: no cover
    raise RuntimeError(f"Unbekannter TELEPHONY_PROVIDER: {settings.telephony_provider}")

orchestrator = Orchestrator(settings, directory, adapter, agent, SessionStore())

_TWIML_MEDIA = "application/xml"


def _twiml(body: str) -> Response:
    return Response(content=body, media_type=_TWIML_MEDIA)


async def _validate_twilio(request: Request, form: dict) -> bool:
    """Prüft die Twilio-Signatur (Schutz vor gefälschten Webhooks)."""
    if not isinstance(adapter, TwilioAdapter):
        return True
    signature = request.headers.get("X-Twilio-Signature", "")
    # Twilio signiert die öffentliche URL; respektiere Proxy-Header.
    url = str(request.url)
    return adapter.validate_signature(url, form, signature)


# --- Routen ------------------------------------------------------------------
@app.get("/health")
async def health() -> JSONResponse:
    return JSONResponse(
        {
            "status": "ok",
            "provider": settings.telephony_provider,
            "company": directory.company_name,
            "departments": [d.id for d in directory.departments],
        }
    )


@app.post("/voice/incoming")
async def voice_incoming(request: Request) -> Response:
    """Twilio ruft dies bei einem eingehenden Anruf auf."""
    form = dict(await request.form())
    if not await _validate_twilio(request, form):
        return PlainTextResponse("Ungültige Signatur", status_code=403)
    return _twiml(orchestrator.handle_incoming(form))


@app.post("/voice/handle")
async def voice_handle(request: Request) -> Response:
    """Wird nach jeder Spracherfassung des Anrufers aufgerufen."""
    form = dict(await request.form())
    if not await _validate_twilio(request, form):
        return PlainTextResponse("Ungültige Signatur", status_code=403)
    return _twiml(await orchestrator.handle_speech(form))


@app.post("/voice/after-transfer")
async def voice_after_transfer(request: Request) -> Response:
    """Wird nach Abschluss einer Weiterleitung aufgerufen."""
    form = dict(await request.form())
    if not await _validate_twilio(request, form):
        return PlainTextResponse("Ungültige Signatur", status_code=403)
    return _twiml(await orchestrator.handle_after_transfer(form))
