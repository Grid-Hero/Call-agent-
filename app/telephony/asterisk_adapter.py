"""Asterisk/FreeSWITCH-Adapter (Telekom SIP-Trunk) – Gerüst.

Für die direkte Anbindung einer Telekom-PBX ohne CPaaS. Die Echtzeit-
Audioverarbeitung läuft hier anders als bei Twilio:

  Telekom SIP-Trunk  ->  Asterisk (chan_pjsip)
                         |
                         |-- ARI (Asterisk REST Interface) für Anrufsteuerung
                         |-- AudioSocket / externalMedia für rohes Audio
                         v
                     STT (z.B. Whisper/Deepgram)  ->  CallAgent (Claude)  ->  TTS

Umsetzungshinweise:
  * dialplan: eingehende Anrufe an Stasis(call-agent) übergeben.
  * Über ARI auf 'StasisStart' reagieren, externalMedia-Kanal für Audio öffnen.
  * Audio-Frames an einen STT-Stream geben; erkannte Sätze als Turn(CALLER)
    in die CallSession schreiben und denselben CallAgent.decide() nutzen wie
    der Twilio-Pfad.
  * Bei action=transfer den Anruf via ARI 'channels/{id}/redirect' bzw. ein
    Bridge zur Zielnummer aufbauen.

Dieses Gerüst hält die Schnittstelle stabil; die Geschäftslogik in app/ai und
app/notify wird unverändert wiederverwendet.
"""

from __future__ import annotations

from app.config import Settings
from app.telephony.base import TelephonyAdapter


class AsteriskAdapter(TelephonyAdapter):
    def __init__(self, settings: Settings):
        self.settings = settings

    def _not_implemented(self) -> str:
        raise NotImplementedError(
            "Asterisk-Adapter ist ein Gerüst. Siehe Modul-Dokumentation und README "
            "(Abschnitt 'Weg B: Telekom-PBX via Asterisk') für die Umsetzung."
        )

    def greeting_response(self, greeting_text, gather_action_url, language):  # noqa: D102
        return self._not_implemented()

    def continue_response(self, reply_text, gather_action_url, language):  # noqa: D102
        return self._not_implemented()

    def transfer_response(self, reply_text, target_number, language, status_callback_url):  # noqa: D102
        return self._not_implemented()

    def hangup_response(self, reply_text, language):  # noqa: D102
        return self._not_implemented()

    def parse_incoming(self, form):  # noqa: D102
        return self._not_implemented()

    def parse_speech(self, form):  # noqa: D102
        return self._not_implemented()
