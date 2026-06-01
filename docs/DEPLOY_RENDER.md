# Deployment auf Render 🚀

Render holt den Code aus deinem GitHub-Repo, startet die App dauerhaft und gibt
dir eine öffentliche HTTPS-Adresse für Twilio. Deine Keys trägst du **im
Render-Dashboard** ein – sicher, nicht im Code, nicht im Chat.

> **Warum nicht „direkt auf GitHub"?** GitHub speichert nur den Code. Render ist
> der Ort, der ihn **ausführt** und für Twilio erreichbar macht.

---

## Voraussetzungen
- Dein Code ist auf GitHub (✅ ist er – Repo `Grid-Hero/Call-agent-`).
- Die Datei `render.yaml` liegt im Repo (✅ habe ich angelegt).
- Du hast deine Keys griffbereit (Anthropic, Twilio, SMTP).

---

## Schritt 1 – Render-Konto anlegen
1. Gehe auf **https://render.com** → **„Get Started"**.
2. Mit **GitHub** anmelden (dann kann Render dein Repo lesen).

## Schritt 2 – Repo verbinden (Blueprint)
1. Im Render-Dashboard: **„New +"** → **„Blueprint"**.
2. Repository **`Grid-Hero/Call-agent-`** auswählen.
   - Branch: `claude/peaceful-hamilton-iztZf` (oder nach Merge `main`).
3. Render erkennt die `render.yaml` automatisch → **„Apply"**.

## Schritt 3 – Keys eintragen (das Wichtigste 🔑)
Render fragt beim ersten Deploy nach allen Werten, die in `render.yaml` als
`sync: false` markiert sind. Trage sie in die Eingabemaske ein:

| Variable | Wert |
|----------|------|
| `ANTHROPIC_API_KEY` | dein Claude-Key (`sk-ant-…`) |
| `TWILIO_ACCOUNT_SID` | `AC…` |
| `TWILIO_AUTH_TOKEN` | dein Twilio-Token |
| `TWILIO_PHONE_NUMBER` | `+49…` |
| `SMTP_HOST` | z. B. `smtp.office365.com` |
| `SMTP_USERNAME` | deine Mailadresse |
| `SMTP_PASSWORD` | Mail-Passwort / App-Passwort |
| `EMAIL_FROM` | Absenderadresse |
| `EMAIL_FALLBACK_TO` | Zentrale-Adresse |

Optional (nur falls genutzt): `ELEVENLABS_API_KEY`, `ELEVENLABS_VOICE_ID`,
`DEEPGRAM_API_KEY`.

> Diese Werte werden bei Render **verschlüsselt** gespeichert und tauchen nie im
> Code oder auf GitHub auf. Du kannst sie jederzeit im Dashboard ändern.

## Schritt 4 – Deploy abwarten
Render baut und startet die App (1–3 Min). Wenn „Live", bekommst du eine URL wie:
```
https://call-agent-xxxx.onrender.com
```
Test: Rufe `https://call-agent-xxxx.onrender.com/health` im Browser auf →
sollte `{"status":"ok",...}` zeigen.

> **APP_BASE_URL** musst du **nicht** setzen – die App erkennt die Render-URL
> automatisch (`RENDER_EXTERNAL_URL`).

## Schritt 5 – Twilio auf die Render-URL zeigen
1. Twilio Console → **Phone Numbers** → deine Nummer.
2. **„A call comes in"** → **Webhook** →
   `https://call-agent-xxxx.onrender.com/voice/incoming` → **HTTP POST**.
3. Speichern.

## Schritt 6 – Testanruf ✅
Ruf deine Twilio-Nummer an. Der Agent meldet sich, versteht dein Anliegen und
stellt durch oder schickt die Zusammenfassungs-Mail.

---

## Wichtige Hinweise

- **Free-Plan** schläft bei Inaktivität ein → der erste Anruf nach einer Pause
  kann ins Leere laufen. Für echten Telefonbetrieb mindestens den **Starter-Plan**
  nutzen (in `render.yaml` bereits `plan: starter`).
- **Region Frankfurt** ist gesetzt (EU – näher an Telekom, besser für DSGVO).
- **Logs ansehen:** Render-Dashboard → dein Service → **„Logs"**. Dort siehst du
  jeden Anruf und eventuelle Fehler.
- **Keys ändern:** Dashboard → Service → **„Environment"** → Wert bearbeiten →
  Render deployt automatisch neu.

## Troubleshooting

| Problem | Lösung |
|---------|--------|
| `/health` lädt nicht | Logs prüfen; Build-Fehler? Richtiger Branch gewählt? |
| Agent meldet sich nicht | Twilio-Webhook-URL korrekt (mit `/voice/incoming`)? |
| „Ungültige Signatur" | Normal nur bei Manipulation; URL muss exakt die Render-URL sein |
| Keine E-Mail | SMTP-Daten prüfen (Logs); bei Google/MS App-Passwort nötig |
| Claude antwortet nicht | Anthropic-Guthaben aufgeladen? Key korrekt eingetragen? |
