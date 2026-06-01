# Einrichtung Schritt für Schritt 🛠️

Diese Anleitung führt dich von Null bis zum ersten Testanruf. Folge den
Schritten der Reihe nach. Jeder Key wird genau dort erklärt, wo du ihn brauchst.

> **Tipp:** Fang mit dem **Minimal-Setup** an (Schritte 1–6). Schöne Stimme
> (ElevenLabs) und Echtzeit-Modus (Deepgram) kannst du später per `.env`-Schalter
> dazunehmen – ohne Code-Änderung.

---

## Übersicht: Welche Keys brauchst du?

| # | Dienst | Pflicht? | Wofür |
|---|--------|----------|-------|
| 1 | **Anthropic** | ✅ immer | Versteht das Anliegen, erstellt Zusammenfassung |
| 2 | **Twilio** | ✅ immer | Nimmt Anrufe an, stellt durch |
| 3 | **SMTP / E-Mail** | ✅ immer | Versendet die Zusammenfassung an Mitarbeiter |
| 4 | **ElevenLabs** | ⚪ optional | Natürliche Stimme statt Standard-Twilio-Stimme |
| 5 | **Deepgram** | ⚪ optional | Nur für Echtzeit-Modus (`CONVERSATION_MODE=realtime`) |

---

## Schritt 0 – Projekt vorbereiten

```bash
git clone <repo-url>
cd Call-agent-
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Jetzt liegt eine `.env` bereit. Die füllen wir in den nächsten Schritten.

---

## Schritt 1 – Anthropic-Key (Claude) ✅

**Wofür:** Das „Gehirn" des Agents.

1. Gehe auf **https://console.anthropic.com**
2. Konto anlegen / einloggen.
3. Links im Menü **„API Keys"** → **„Create Key"**.
4. Namen vergeben (z. B. `call-agent`), Key kopieren (beginnt mit `sk-ant-...`).
5. **Wichtig:** Unter **„Billing"** eine Zahlungsmethode hinterlegen und etwas
   Guthaben aufladen (ohne Guthaben funktionieren die API-Aufrufe nicht).

In die `.env`:
```bash
ANTHROPIC_API_KEY=sk-ant-xxxxxxxxxxxxxxxxxxxx
```

> 💡 Den Key bekommst du **nur einmal** angezeigt – sofort kopieren.

---

## Schritt 2 – Twilio (Telefonie) ✅

**Wofür:** Anrufe annehmen und weiterleiten.

### 2a) Konto + Zugangsdaten
1. Gehe auf **https://www.twilio.com** → **„Sign up"**.
2. Nach dem Login siehst du im **Dashboard** (Console) zwei Werte:
   - **Account SID** (beginnt mit `AC...`)
   - **Auth Token** (auf „Show" klicken)

In die `.env`:
```bash
TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_AUTH_TOKEN=dein_auth_token
```

### 2b) Telefonnummer besorgen
**Option A – Twilio-Nummer (am schnellsten zum Testen):**
1. In der Console: **Phone Numbers** → **Manage** → **Buy a number**.
2. Land **Deutschland** wählen, eine Nummer mit **Voice**-Fähigkeit kaufen.
3. Nummer in die `.env` eintragen (Format `+49...`):
```bash
TWILIO_PHONE_NUMBER=+4930xxxxxxxx
```

**Option B – Eure Telekom-Nummer (BYOC):**
- Siehe README, Abschnitt „Telekom-PBX anbinden". Dafür hinterlegst du euren
  Telekom-SIP-Trunk unter *Elastic SIP Trunking → BYOC*. Kein extra Key, nur
  Konfiguration. Empfehlung: erst mit Option A testen, dann auf Telekom umstellen.

---

## Schritt 3 – SMTP / E-Mail ✅

**Wofür:** Versand der Gesprächszusammenfassung an den zuständigen Mitarbeiter.

Du brauchst **keinen neuen Dienst** – eure vorhandene Firmen-Mailadresse reicht.
Trage die SMTP-Daten eures Mailproviders ein. Beispiele:

| Provider | SMTP_HOST | SMTP_PORT | TLS |
|----------|-----------|-----------|-----|
| Microsoft 365 | `smtp.office365.com` | 587 | ja |
| Google Workspace | `smtp.gmail.com` | 587 | ja |
| Telekom Business | `securesmtp.t-online.de` | 587 | ja |
| Mailgun/Postmark | (laut Anbieter) | 587 | ja |

In die `.env`:
```bash
SMTP_HOST=smtp.office365.com
SMTP_PORT=587
SMTP_USERNAME=callagent@deine-firma.de
SMTP_PASSWORD=dein_mail_passwort
SMTP_USE_TLS=true
EMAIL_FROM=callagent@deine-firma.de
EMAIL_FALLBACK_TO=zentrale@deine-firma.de
```

> ⚠️ **Google/Microsoft:** Bei aktivierter 2-Faktor-Anmeldung brauchst du ein
> **App-Passwort** (nicht dein normales Login-Passwort). Das erstellst du in den
> Sicherheitseinstellungen des jeweiligen Kontos.

---

## Schritt 4 – Mitarbeiterverzeichnis pflegen ✅

Öffne `config/directory.yaml` und trage **eure echten Daten** ein:
- Firmenname + Begrüßungstext
- Abteilungen mit `email` (Empfänger der Zusammenfassung), `phone` (Zielnummer
  für Weiterleitung, Format `+49...`) und `transfer_enabled` (durchstellen ja/nein)
- `fallback` (wenn keine Abteilung passt)
- `business_hours` (Geschäftszeiten)

---

## Schritt 5 – App öffentlich erreichbar machen ✅

Twilio muss deine App über das Internet erreichen. Zum Testen am einfachsten
mit **ngrok**:

1. Konto auf **https://ngrok.com** anlegen, ngrok installieren.
2. App lokal starten:
   ```bash
   uvicorn app.main:app --port 8000
   ```
3. In einem zweiten Terminal:
   ```bash
   ngrok http 8000
   ```
4. ngrok zeigt eine URL wie `https://abc123.ngrok-free.app`. Diese in die `.env`:
   ```bash
   APP_BASE_URL=https://abc123.ngrok-free.app
   ```
5. App nach `.env`-Änderung neu starten.

---

## Schritt 6 – Twilio-Nummer mit der App verbinden ✅

### Vorher: Keys prüfen

Bevor du anrufst, prüfe mit dem mitgelieferten Skript, ob alle Zugänge
funktionieren (zeigt ✅/❌ pro Dienst, **ohne** Key-Werte auszugeben):

```bash
python scripts/check_setup.py
```

Erst weitermachen, wenn alle relevanten Punkte ✅ sind.

### Webhook setzen

1. Twilio Console → **Phone Numbers** → **Manage** → deine Nummer anklicken.
2. Abschnitt **„Voice Configuration"** → **„A call comes in"**:
   - Typ: **Webhook**
   - URL: `https://abc123.ngrok-free.app/voice/incoming`
   - Methode: **HTTP POST**
3. **Speichern.**

### ✅ Erster Testanruf
Ruf deine Twilio-Nummer an. Der Agent sollte sich melden, dein Anliegen
verstehen und entweder durchstellen oder eine Zusammenfassungs-Mail senden.

**Damit ist das Minimal-Setup fertig.** 🎉

---

## Schritt 7 (optional) – ElevenLabs-Stimme ⚪

**Wofür:** Natürlich klingende Stimme statt der Standard-Twilio-Stimme.

1. Konto auf **https://elevenlabs.io** anlegen.
2. Rechts oben **Profil** → **„API Keys"** → Key kopieren.
3. **Voice-ID** finden: **„Voices"** / **Voice Library** → gewünschte Stimme →
   bei der Stimme auf **„ID"** (oder Details) → die Voice-ID kopieren.
4. In die `.env`:
   ```bash
   TTS_PROVIDER=elevenlabs
   ELEVENLABS_API_KEY=dein_elevenlabs_key
   ELEVENLABS_VOICE_ID=die_voice_id
   ELEVENLABS_MODEL=eleven_multilingual_v2
   ```
5. App neu starten. Fällt ElevenLabs aus, spricht automatisch wieder die
   Twilio-Stimme – der Anruf bricht nie ab.

---

## Schritt 8 (optional) – Echtzeit-Modus (Deepgram) ⚪

**Wofür:** Natürliche, unterbrechbare Dialoge (Anrufer kann den Agent
unterbrechen). Benötigt **ElevenLabs (Schritt 7)** + **Deepgram**.

1. Konto auf **https://console.deepgram.com** anlegen.
2. **„API Keys"** → **„Create a New API Key"** → Key kopieren.
3. (Beim Start gibt es i. d. R. ein Gratis-Guthaben.)
4. In die `.env`:
   ```bash
   CONVERSATION_MODE=realtime
   DEEPGRAM_API_KEY=dein_deepgram_key
   DEEPGRAM_MODEL=nova-2
   DEEPGRAM_LANGUAGE=de
   ```
5. App neu starten. Beim nächsten Anruf verbindet Twilio automatisch den
   Echtzeit-Audio-Stream (`wss://<APP_BASE_URL>/media`).

> ⚠️ Für den Echtzeit-Modus muss `APP_BASE_URL` per **HTTPS/WSS** erreichbar
> sein (ngrok erfüllt das).

---

## Fertige `.env` – Beispiele

### Minimal (empfohlen für den Start)
```bash
APP_BASE_URL=https://abc123.ngrok-free.app
CONVERSATION_MODE=gather
TELEPHONY_PROVIDER=twilio

ANTHROPIC_API_KEY=sk-ant-...

TWILIO_ACCOUNT_SID=AC...
TWILIO_AUTH_TOKEN=...
TWILIO_PHONE_NUMBER=+4930...

TTS_PROVIDER=twilio

SMTP_HOST=smtp.office365.com
SMTP_PORT=587
SMTP_USERNAME=callagent@deine-firma.de
SMTP_PASSWORD=...
SMTP_USE_TLS=true
EMAIL_FROM=callagent@deine-firma.de
EMAIL_FALLBACK_TO=zentrale@deine-firma.de
```

### Voller Ausbau (Echtzeit + ElevenLabs)
```bash
# ... alles aus „Minimal", plus:
CONVERSATION_MODE=realtime
TTS_PROVIDER=elevenlabs
ELEVENLABS_API_KEY=...
ELEVENLABS_VOICE_ID=...
DEEPGRAM_API_KEY=...
```

---

## Checkliste

- [ ] Anthropic-Key + Guthaben aufgeladen
- [ ] Twilio Account SID + Auth Token
- [ ] Twilio-Nummer (oder Telekom-BYOC)
- [ ] SMTP-Zugang (ggf. App-Passwort)
- [ ] `config/directory.yaml` mit echten Abteilungen/Nummern
- [ ] `APP_BASE_URL` (ngrok-URL) gesetzt
- [ ] Twilio-Nummer-Webhook auf `…/voice/incoming` gesetzt
- [ ] Testanruf erfolgreich
- [ ] (optional) ElevenLabs-Key + Voice-ID
- [ ] (optional) Deepgram-Key + `CONVERSATION_MODE=realtime`

---

## Häufige Stolpersteine

| Problem | Ursache / Lösung |
|---------|------------------|
| Agent meldet sich nicht | Webhook-URL falsch oder App nicht öffentlich erreichbar (ngrok läuft?) |
| „Ungültige Signatur" (403) | `APP_BASE_URL` muss exakt mit der Twilio-Webhook-URL übereinstimmen (https, keine Tippfehler) |
| Keine E-Mail kommt an | SMTP-Daten/Passwort prüfen; bei Google/MS App-Passwort nötig; Spam-Ordner checken |
| Claude antwortet nicht | Anthropic-Guthaben aufgeladen? Key korrekt? |
| Keine ElevenLabs-Stimme | Key/Voice-ID fehlt → fällt automatisch auf Twilio-Stimme zurück (Logs prüfen) |
| Echtzeit-Modus stumm | Deepgram- **und** ElevenLabs-Key gesetzt? `APP_BASE_URL` per HTTPS? |
