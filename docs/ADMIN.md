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

## ⭐ Dauerhafte Speicherung in GitHub (empfohlen)

Standardmäßig schreibt `/admin` in die lokale Datei – auf dem **Render Free-Plan**
ist die aber flüchtig (Änderungen gehen bei Neustart/Deploy verloren).

Mit der **GitHub-Speicherung** werden Änderungen stattdessen **als Commit ins
Repo** geschrieben und beim Start von dort geladen: dauerhaft **und** versioniert.

**Einrichten:**
1. **GitHub-Token erstellen:** GitHub → *Settings* → *Developer settings* →
   *Fine-grained tokens* → *Generate new token*
   - **Repository access:** nur `Grid-Hero/Call-agent-`
   - **Permissions:** *Contents* → **Read and write**
   - Token kopieren (beginnt mit `github_pat_…`)
2. **In Render → Environment** setzen:
   - `GITHUB_TOKEN` = dein Token
   - `GITHUB_REPO` = `Grid-Hero/Call-agent-`
   - `GITHUB_BRANCH` = der **tatsächlich deployte Branch**
   - (optional `GITHUB_CONFIG_PATH`, Standard: `config/directory.yaml`)
3. Speichern → ab jetzt landet jede `/admin`-Änderung als Commit im Repo.

Die Admin-Seite zeigt oben an, ob „Speicherung: GitHub" aktiv ist.

> **Hinweis:** Ist in Render **Auto-Deploy** aktiv, löst jeder Speichern-Commit
> einen kurzen Re-Deploy aus (die Änderung ist durch das sofortige Live-Update
> aber bereits aktiv). Wer das vermeiden will, nutzt einen separaten
> Konfig-Branch oder schaltet Auto-Deploy ab.

## Alternative: Persistente Disk

Statt GitHub geht auch eine **persistente Disk** (ab Starter-Plan): Disk z.B.
unter `/data` mounten und `DIRECTORY_PATH=/data/directory.yaml` setzen. Dann
überleben Änderungen ebenfalls Neustarts – ohne GitHub-Token.
