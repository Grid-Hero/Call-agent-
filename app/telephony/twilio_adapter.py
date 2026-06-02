"""Twilio-Adapter: erzeugt TwiML und prüft Webhook-Signaturen.

Spracherfassung über <Gather input="speech"> (Twilios eingebaute Erkennung,
unterstützt de-DE) und Antworten über <Say>. So bleibt der MVP ohne komplexes
Echtzeit-Audio-Streaming und ist sofort lauffähig.

Telekom-Anbindung: Über Twilio "Elastic SIP Trunking / BYOC" kann ein
Telekom-SIP-Trunk auf eine Twilio-Nummer gelegt werden, ohne diesen Code zu
ändern – die Webhooks bleiben identisch.
"""

from __future__ import annotations

from typing import Optional

from twilio.request_validator import RequestValidator
from twilio.twiml.voice_response import Connect, Gather, VoiceResponse

from app.config import Settings
from app.telephony.base import TelephonyAdapter

# Twilio Speech-to-Text Modell mit guter Performance für Telefonie.
_SPEECH_MODEL = "phone_call"


class TwilioAdapter(TelephonyAdapter):
    def __init__(self, settings: Settings):
        self.settings = settings
        self._validator = RequestValidator(settings.twilio_auth_token)

    # --- Signaturprüfung -----------------------------------------------------
    def validate_signature(self, url: str, form: dict, signature: str) -> bool:
        """Prüft die X-Twilio-Signature, um gefälschte Webhooks abzuwehren."""
        if not self.settings.twilio_validate_signature:
            return True
        return self._validator.validate(url, form, signature or "")

    # --- TwiML-Erzeugung -----------------------------------------------------
    def _gather(self, response: VoiceResponse, action_url: str, language: str) -> Gather:
        gather = Gather(
            input="speech",
            action=action_url,
            method="POST",
            language=language,
            speech_model=_SPEECH_MODEL,
            speech_timeout="auto",
            action_on_empty_result=True,
        )
        response.append(gather)
        return gather

    def _speak(self, container, text: str, language: str, audio_url: Optional[str]) -> None:
        """Spielt vorab erzeugtes Audio (z.B. ElevenLabs) ab oder spricht via Twilio."""
        if audio_url:
            container.play(audio_url)
        else:
            container.say(text, language=language, voice=self.settings.twilio_voice)

    def greeting_response(self, greeting_text, gather_action_url, language, audio_url=None):
        response = VoiceResponse()
        gather = self._gather(response, gather_action_url, language)
        self._speak(gather, greeting_text, language, audio_url)
        return str(response)

    def continue_response(self, reply_text, gather_action_url, language, audio_url=None):
        response = VoiceResponse()
        gather = self._gather(response, gather_action_url, language)
        self._speak(gather, reply_text, language, audio_url)
        return str(response)

    def transfer_response(self, reply_text, target_number, language, status_callback_url, audio_url=None):
        response = VoiceResponse()
        self._speak(response, reply_text, language, audio_url)
        dial = response.dial(
            timeout=25,
            action=status_callback_url,  # Wird nach dem Telefonat aufgerufen
            method="POST",
            caller_id=self.settings.twilio_phone_number or None,
        )
        dial.number(target_number)
        return str(response)

    def hangup_response(self, reply_text, language, audio_url=None):
        response = VoiceResponse()
        self._speak(response, reply_text, language, audio_url)
        response.hangup()
        return str(response)

    def realtime_connect_response(self, stream_url: str, caller_number: str = "") -> str:
        """Verbindet den Anruf mit dem Echtzeit-Media-Stream (WebSocket).

        Nach Ende des Streams folgt <Hangup>, sodass der Anruf beendet wird,
        sofern er nicht zuvor per REST-API weitergeleitet wurde.
        """
        response = VoiceResponse()
        connect = Connect()
        stream = connect.stream(url=stream_url)
        if caller_number:
            stream.parameter(name="from", value=caller_number)
        response.append(connect)
        response.hangup()
        return str(response)

    # --- Eingehende Daten parsen --------------------------------------------
    def parse_incoming(self, form: dict) -> tuple[str, str, str]:
        return (
            form.get("CallSid", ""),
            form.get("From", "unbekannt"),
            form.get("To", ""),
        )

    def parse_speech(self, form: dict) -> str:
        return form.get("SpeechResult", "")
