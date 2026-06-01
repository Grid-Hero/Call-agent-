"""Twilio-Adapter: erzeugt TwiML und prüft Webhook-Signaturen.

Spracherfassung über <Gather input="speech"> (Twilios eingebaute Erkennung,
unterstützt de-DE) und Antworten über <Say>. So bleibt der MVP ohne komplexes
Echtzeit-Audio-Streaming und ist sofort lauffähig.

Telekom-Anbindung: Über Twilio "Elastic SIP Trunking / BYOC" kann ein
Telekom-SIP-Trunk auf eine Twilio-Nummer gelegt werden, ohne diesen Code zu
ändern – die Webhooks bleiben identisch.
"""

from __future__ import annotations

from twilio.request_validator import RequestValidator
from twilio.twiml.voice_response import Gather, VoiceResponse

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

    def greeting_response(self, greeting_text: str, gather_action_url: str, language: str) -> str:
        response = VoiceResponse()
        gather = self._gather(response, gather_action_url, language)
        gather.say(greeting_text, language=language)
        return str(response)

    def continue_response(self, reply_text: str, gather_action_url: str, language: str) -> str:
        response = VoiceResponse()
        gather = self._gather(response, gather_action_url, language)
        gather.say(reply_text, language=language)
        return str(response)

    def transfer_response(self, reply_text: str, target_number: str, language: str, status_callback_url: str) -> str:
        response = VoiceResponse()
        response.say(reply_text, language=language)
        dial = response.dial(
            timeout=25,
            action=status_callback_url,  # Wird nach dem Telefonat aufgerufen
            method="POST",
            caller_id=self.settings.twilio_phone_number or None,
        )
        dial.number(target_number)
        return str(response)

    def hangup_response(self, reply_text: str, language: str) -> str:
        response = VoiceResponse()
        response.say(reply_text, language=language)
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
