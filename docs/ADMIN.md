# Konfigurations-Weboberfläche (`/admin`)

Statt die Datei `config/directory.yaml` von Hand zu editieren, kannst du alles
bequem im Browser pflegen.

## Aktivieren
1. In Render (oder `.env`) ein Passwort setzen:
   - `ADMIN_PASSWORD` = dein Wunschpasswort
   - (optional `ADMIN_USER`, Standard: `admin`)
2. Öffnen: `https://DEINE-RENDER-URL/admin`
3. Anmelden: Benutzer `admin`, dein Passwort.

> Ohne gesetztes `ADMIN_PASSWORD` ist die Seite **deaktiviert** (Schutz vor
> unbefugtem Zugriff).

## Was du dort einstellst
- **Unternehmen:** Firmenname + Begrüßungstext des Agents
- **Geschäftszeiten:** pro Wochentag Öffnungszeiten (leer = geschlossen).
  Außerhalb wird nicht durchgestellt, sondern eine Nachricht aufgenommen.
- **Abteilungen:** Name, Themen/Stichworte (für die Zuordnung durch Claude),
  E-Mail (Empfänger der Zusammenfassung), Telefon (Weiterleitungsziel),
  Durchstellen ja/nein. Beliebig viele über „+ Abteilung hinzufügen".
- **Fallback:** wohin, wenn keine Abteilung passt.

Nach **Speichern** werden die Änderungen **sofort live** übernommen – kein
Neustart nötig.

## ⚠️ Wichtig: Persistenz auf Render

Auf dem **Free-Plan** ist das Dateisystem **flüchtig**: Änderungen über `/admin`
gelten sofort und bleiben, bis die Instanz neu startet oder neu deployed wird –
**danach sind sie zurückgesetzt** auf den Stand aus dem Git-Repo.

Damit Änderungen dauerhaft bleiben, hast du zwei Optionen:

1. **Persistente Disk (empfohlen, ab Starter-Plan):**
   - In Render eine **Disk** anlegen, z.B. gemountet unter `/data`
   - Umgebungsvariable `DIRECTORY_PATH=/data/directory.yaml` setzen
   - Beim ersten Start einmal die Startwerte dorthin kopieren (oder über `/admin`
     neu eingeben). Ab dann überleben Änderungen Neustarts/Deploys.

2. **Im Repo pflegen:** Änderungen direkt in `config/directory.yaml` committen
   (per Git). Dann sind sie versioniert und nach jedem Deploy aktiv – aber eben
   nicht über die Weboberfläche dauerhaft.

> Für den dauerhaften Produktivbetrieb ist Option 1 (persistente Disk) am
> komfortabelsten: `/admin` bleibt nutzbar **und** Änderungen sind dauerhaft.
