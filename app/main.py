"""FastAPI-Anwendung: empfängt Telefonie-Webhooks und steuert den Anruf."""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request, Response, WebSocket
from fastapi.responses import JSONResponse, PlainTextResponse

from app.admin import create_admin_router
from app.config import get_settings
from app.runtime import Runtime
from app.telephony.twilio_adapter import TwilioAdapter

settings = get_settings()
logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))
logger = logging.getLogger("call-agent")

app = FastAPI(title="Call-Agent", version="0.1.0")

# Zentraler Laufzeit-Container (Verzeichnis, Agent, Adapter, TTS, Orchestrator).
# Über die Admin-Oberfläche (/admin) live neu ladbar.
runtime = Runtime(settings)
app.include_router(create_admin_router(runtime))

_TWIML_MEDIA = "application/xml"


def _twiml(body: str) -> Response:
    return Response(content=body, media_type=_TWIML_MEDIA)


async def _validate_twilio(request: Request, form: dict) -> bool:
    """Prüft die Twilio-Signatur (Schutz vor gefälschten Webhooks).

    Robust gegen Reverse-Proxies (z.B. Render): Twilio signiert die ÖFFENTLICHE
    URL, hinter dem Proxy sieht die App aber oft eine interne. Daher werden
    mehrere plausible URL-Varianten geprüft. Ohne Auth-Token ist keine Prüfung
    möglich – dann wird sie (mit Warnung) übersprungen, statt den Anruf mit
    einem Fehler abzubrechen.
    """
    if not isinstance(runtime.adapter, TwilioAdapter):
        return True
    if not settings.twilio_validate_signature:
        return True
    if not settings.twilio_auth_token:
        logger.warning("Kein TWILIO_AUTH_TOKEN gesetzt – Signaturprüfung übersprungen.")
        return True

    signature = request.headers.get("X-Twilio-Signature", "")
    path_q = request.url.path + (f"?{request.url.query}" if request.url.query else "")
    candidates = [
        f"{settings.effective_base_url}{path_q}",
        str(request.url),
        str(request.url).replace("http://", "https://", 1),
    ]
    for url in candidates:
        if runtime.adapter.validate_signature(url, form, signature):
            return True
    logger.warning("Twilio-Signatur ungültig. Geprüfte URLs: %s", candidates)
    return False


# --- Routen ------------------------------------------------------------------
@app.get("/health")
async def health() -> JSONResponse:
    return JSONResponse(
        {
            "status": "ok",
            "provider": settings.telephony_provider,
            "company": runtime.directory.company_name,
            "departments": [d.id for d in runtime.directory.departments],
        }
    )


@app.post("/voice/incoming")
async def voice_incoming(request: Request) -> Response:
    """Twilio ruft dies bei einem eingehenden Anruf auf."""
    form = dict(await request.form())
    if not await _validate_twilio(request, form):
        return PlainTextResponse("Ungültige Signatur", status_code=403)

    # Echtzeit-Modus: Anruf mit dem Media Stream (WebSocket) verbinden.
    if settings.conversation_mode == "realtime" and isinstance(runtime.adapter, TwilioAdapter):
        caller = form.get("From", "")
        stream_url = f"{settings.websocket_base_url}/media"
        return _twiml(runtime.adapter.realtime_connect_response(stream_url, caller))

    return _twiml(await runtime.orchestrator.handle_incoming(form))


@app.post("/voice/handle")
async def voice_handle(request: Request) -> Response:
    """Wird nach jeder Spracherfassung des Anrufers aufgerufen."""
    form = dict(await request.form())
    if not await _validate_twilio(request, form):
        return PlainTextResponse("Ungültige Signatur", status_code=403)
    return _twiml(await runtime.orchestrator.handle_speech(form))


@app.get("/audio/{token}.mp3")
async def serve_audio(token: str) -> Response:
    """Liefert vom TTS-Anbieter (z.B. ElevenLabs) erzeugtes Audio aus.

    Twilio ruft diese URL über <Play> ab. Tokens sind zufällig und kurzlebig.
    """
    item = runtime.audio_store.get(token)
    if item is None:
        return PlainTextResponse("Nicht gefunden oder abgelaufen", status_code=404)
    data, content_type = item
    return Response(content=data, media_type=content_type)


@app.post("/voice/after-transfer")
async def voice_after_transfer(request: Request) -> Response:
    """Wird nach Abschluss einer Weiterleitung aufgerufen (Gather-Modus)."""
    form = dict(await request.form())
    if not await _validate_twilio(request, form):
        return PlainTextResponse("Ungültige Signatur", status_code=403)
    return _twiml(await runtime.orchestrator.handle_after_transfer(form))


@app.websocket("/media")
async def media_stream(websocket: WebSocket) -> None:
    """Twilio Media Stream (Echtzeit-Modus): bidirektionales Audio über WebSocket."""
    await websocket.accept()
    from app.realtime.factory import build_call_control, build_streaming_tts, build_stt
    from app.realtime.session import RealtimeCallSession
    from app.realtime.transport import TwilioWebSocketTransport

    transport = TwilioWebSocketTransport(websocket)
    realtime = RealtimeCallSession(
        settings,
        runtime.directory,
        runtime.agent,
        transport,
        build_stt(settings),
        build_streaming_tts(settings),
        build_call_control(settings),
    )
    try:
        await realtime.run()
    except Exception:  # pragma: no cover - Laufzeitschutz
        logger.exception("Fehler im Media Stream")
        await transport.close()
