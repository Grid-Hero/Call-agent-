# Call-Agent 📞🤖

Ein KI-gestützter Telefonassistent, der eingehende Anrufe **automatisch
annimmt**, das Anliegen versteht und entweder

1. **an die zuständige Person/Abteilung durchstellt** oder
2. eine **Zusammenfassung des Gesprächs erstellt und per E-Mail** an den
   passenden Mitarbeiter weiterleitet.

Die Gesprächslogik und Zusammenfassung übernimmt **Anthropic Claude**, die
Telefonie ist über eine **austauschbare Adapter-Schicht** angebunden
(Twilio out-of-the-box, Asterisk/Telekom-PBX als Gerüst).

---

## Inhaltsverzeichnis
- [Funktionsweise](#funktionsweise)
- [Architektur](#architektur)
- [Telekom-PBX anbinden](#telekom-pbx-anbinden)
- [Schnellstart](#schnellstart)
- [Konfiguration](#konfiguration)
- [Mitarbeiterverzeichnis](#mitarbeiterverzeichnis-anpassen)
- [Tests](#tests)
- [Sicherheit & Datenschutz](#sicherheit--datenschutz)
- [Nächste Schritte / Roadmap](#nächste-schritte--roadmap)

---

## Funktionsweise

```
Anrufer ──► Telefonie (Twilio / Telekom-SIP) ──► Webhook ──► FastAPI-App
                                                               │
                  ┌────────────────────────────────────────────┤
                  ▼                                             ▼
          Claude entscheidet:                          Gesprächs-Session
          continue / transfer /                        (In-Memory-Store)
          message / goodbye
                  │
        ┌─────────┼───────────────┐
        ▼         ▼               ▼
   Rückfrage  Durchstellen   Zusammenfassung
   (weiter    (Dial an        (Claude) ──► E-Mail
    zuhören)   Abteilung)            an Mitarbeiter
```

Pro Anrufer-Äußerung entscheidet Claude über die nächste Aktion:

| Aktion      | Bedeutung                                                        |
|-------------|------------------------------------------------------------------|
| `continue`  | Anliegen unklar → eine gezielte Rückfrage, weiter zuhören         |
| `transfer`  | Anliegen klar + Abteilung durchstellbar → Anruf weiterleiten      |
| `message`   | Nachricht aufnehmen → Zusammenfassung per E-Mail an die Abteilung |
| `goodbye`   | Kein echtes Anliegen / Spam → höflich verabschieden               |

Außerhalb der Geschäftszeiten (in `config/directory.yaml` definiert) wird
**nie durchgestellt**, sondern immer eine Nachricht aufgenommen.

---

## Architektur

| Modul                          | Aufgabe                                                  |
|--------------------------------|----------------------------------------------------------|
| `app/main.py`                  | FastAPI-App, Telefonie-Webhooks, Signaturprüfung         |
| `app/orchestrator.py`          | Anruf-Ablauf, Session-Verwaltung, verbindet alle Teile   |
| `app/ai/agent.py`              | Claude: Routing-Entscheidung + Zusammenfassung (Tool-Use)|
| `app/telephony/base.py`        | Abstrakte Telefonie-Schnittstelle                        |
| `app/telephony/twilio_adapter.py` | Twilio-Implementierung (TwiML, Signaturprüfung)       |
| `app/telephony/asterisk_adapter.py` | Gerüst für Telekom-PBX via Asterisk                 |
| `app/notify/email.py`          | E-Mail-Versand der Zusammenfassung (SMTP)                |
| `app/directory.py`             | Mitarbeiter-/Abteilungsverzeichnis, Geschäftszeiten      |
| `app/models.py`                | Domänenmodelle (Session, Entscheidung, Zusammenfassung)  |
| `config/directory.yaml`        | Abteilungen, Routing, Geschäftszeiten (zentral pflegbar) |

Die **Geschäftslogik ist anbieterunabhängig**: Ein Wechsel des Telefonie-
Anbieters erfordert nur einen neuen Adapter, kein Eingriff in `app/ai` oder
`app/notify`.

---

## Telekom-PBX anbinden

Es gibt zwei Wege, eure Telekom-Anlage anzubinden:

### Weg A – Telekom SIP-Trunk über Twilio (empfohlen für den Start)
Ihr behaltet eure **Telekom-Rufnummer**, nutzt aber Twilios entwickler-
freundliche Sprach-API:

```
Telekom SIP-Trunk ──► Twilio Elastic SIP Trunking (BYOC) ──► diese App
```

1. Twilio-Konto anlegen, **Elastic SIP Trunking** aktivieren.
2. Unter *BYOC (Bring Your Own Carrier)* den Telekom-SIP-Trunk hinterlegen
   (DeutschlandLAN SIP-Trunk / CompanyFlex).
3. Die eingehende Nummer auf die Webhook-URL `…/voice/incoming` zeigen lassen.

**Kein Code-Eingriff nötig** – der bestehende Twilio-Adapter funktioniert.

### Weg B – Direkt via Asterisk/FreeSWITCH (volle Kontrolle, EU-lokal)
Keine CPaaS-Gebühren, Audio bleibt im eigenen Haus:

```
Telekom SIP-Trunk ──► Asterisk (chan_pjsip) ──► ARI + AudioSocket
                                                  │
                          STT (Whisper/Deepgram) ─┴─► CallAgent (Claude) ─► TTS
```

Der `AsteriskAdapter` ist als Gerüst angelegt (`app/telephony/asterisk_adapter.py`).
Die Geschäftslogik (`app/ai`, `app/notify`, `app/orchestrator`) wird dabei
**unverändert wiederverwendet** – es muss nur die Audio-/Steuerungsbrücke
(ARI + STT/TTS) implementiert werden. Hinweise stehen im Modul-Docstring.

---

## Schnellstart

```bash
# 1. Virtuelle Umgebung & Abhängigkeiten
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 2. Konfiguration anlegen
cp .env.example .env
#   -> ANTHROPIC_API_KEY, TWILIO_*, SMTP_* eintragen

# 3. Verzeichnis anpassen
#   -> config/directory.yaml (Abteilungen, Nummern, E-Mails)

# 4. Lokal starten
uvicorn app.main:app --reload --port 8000

# 5. Öffentlich erreichbar machen (für Twilio-Webhooks), z.B.:
#   ngrok http 8000
#   -> APP_BASE_URL in .env auf die ngrok-URL setzen
#   -> in der Twilio-Nummer "A call comes in" = https://<url>/voice/incoming
```

Gesundheitscheck: `GET http://localhost:8000/health`

---

## Konfiguration

Alle Einstellungen über Umgebungsvariablen (`.env`) – siehe `.env.example`.
Wichtigste Werte:

| Variable                  | Zweck                                               |
|---------------------------|-----------------------------------------------------|
| `APP_BASE_URL`            | Öffentliche URL der App (für Webhook-Callbacks)      |
| `TELEPHONY_PROVIDER`      | `twilio` oder `asterisk`                             |
| `TWILIO_*`                | Twilio-Zugangsdaten + eingehende Nummer             |
| `TWILIO_VALIDATE_SIGNATURE` | Webhook-Signaturprüfung (in Produktion `true`)    |
| `ANTHROPIC_API_KEY`       | Claude-API-Schlüssel                                |
| `ANTHROPIC_MODEL`         | Claude-Modell (Standard: `claude-opus-4-8`)         |
| `SMTP_*`, `EMAIL_*`       | E-Mail-Versand der Zusammenfassungen                |
| `DIRECTORY_PATH`          | Pfad zur Verzeichnis-YAML                           |

---

## Mitarbeiterverzeichnis anpassen

`config/directory.yaml` ist die zentrale Stelle für eure Organisation:

- **`departments`** – Abteilungen mit `topics` (Stichworte, anhand derer Claude
  zuordnet), `email` (Empfänger der Zusammenfassung), `phone` (Zielnummer für
  Weiterleitung) und `transfer_enabled` (darf direkt durchgestellt werden?).
- **`fallback`** – Ziel, wenn keine Abteilung eindeutig passt.
- **`business_hours`** – Geschäftszeiten pro Wochentag; außerhalb wird nur eine
  Nachricht aufgenommen.

Änderungen an der YAML wirken nach einem Neustart der App.

---

## Tests

```bash
source .venv/bin/activate
pytest
```

Die Tests laufen **ohne externe API-Schlüssel** (Claude wird gemockt, E-Mail
deaktiviert) und decken Verzeichnis, Geschäftszeiten, TwiML-Erzeugung und den
Anruf-Ablauf (continue/transfer/message + Fallback) ab.

---

## Sicherheit & Datenschutz

- **Webhook-Signaturen** werden über `X-Twilio-Signature` geprüft
  (`TWILIO_VALIDATE_SIGNATURE=true` in Produktion).
- **Geheimnisse** stehen ausschließlich in `.env` (per `.gitignore`
  ausgeschlossen) – nie committen.
- **DSGVO**: Anrufe enthalten personenbezogene Daten. Empfehlungen:
  - Anrufer zu Gesprächsbeginn über die KI-Bearbeitung informieren
    (Begrüßungstext in `directory.yaml` anpassen).
  - Auftragsverarbeitungsverträge (AVV) mit Twilio/Anthropic prüfen; für
    strenge EU-Anforderungen Weg B (Asterisk, EU-Hosting) erwägen.
  - Aufbewahrungsfristen für Protokolle/Zusammenfassungen definieren.

---

## Nächste Schritte / Roadmap

- [ ] **Persistenz**: In-Memory-`SessionStore` durch Redis oder Supabase
      ersetzen (für Skalierung über mehrere Instanzen).
- [ ] **Echtzeit-Audio**: Twilio Media Streams + Deepgram für natürlichere,
      unterbrechbare Dialoge (statt `<Gather>`).
- [ ] **Weitere Kanäle**: Zusammenfassung zusätzlich in Slack/Teams.
- [ ] **Asterisk-Adapter** vollständig implementieren (Weg B).
- [ ] **CRM-Anbindung**: erkannte Anliegen direkt als Ticket/Lead anlegen.
- [ ] **Mehrsprachigkeit**: Spracherkennung des Anrufers, dynamische `language`.
```
