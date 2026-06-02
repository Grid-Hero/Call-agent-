"""Passwortgeschützte Admin-Weboberfläche zum Konfigurieren des Verzeichnisses.

Erreichbar unter ``/admin`` (HTTP-Basic-Auth). Bearbeitet Firmenname,
Begrüßung, Geschäftszeiten und Abteilungen und schreibt sie nach
``directory.yaml`` zurück; danach lädt die Runtime live neu.
"""

from __future__ import annotations

import asyncio
import logging
import re
import secrets

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from app.directory import (
    BusinessHours,
    Department,
    Directory,
    Fallback,
)
from app.runtime import Runtime

_WEEKDAYS = [
    ("monday", "Montag"),
    ("tuesday", "Dienstag"),
    ("wednesday", "Mittwoch"),
    ("thursday", "Donnerstag"),
    ("friday", "Freitag"),
    ("saturday", "Samstag"),
    ("sunday", "Sonntag"),
]

_security = HTTPBasic(auto_error=False)


def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
    return slug or "abteilung"


def _esc(value: str) -> str:
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def create_admin_router(runtime: Runtime) -> APIRouter:
    router = APIRouter(prefix="/admin", tags=["admin"])
    settings = runtime.settings

    def require_admin(credentials: HTTPBasicCredentials = Depends(_security)) -> bool:
        if not settings.admin_password:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Admin-Oberfläche deaktiviert: ADMIN_PASSWORD setzen.",
            )
        if credentials is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Anmeldung erforderlich",
                headers={"WWW-Authenticate": "Basic"},
            )
        user_ok = secrets.compare_digest(credentials.username, settings.admin_user)
        pw_ok = secrets.compare_digest(credentials.password, settings.admin_password)
        if not (user_ok and pw_ok):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Falsche Zugangsdaten",
                headers={"WWW-Authenticate": "Basic"},
            )
        return True

    @router.get("", response_class=HTMLResponse)
    async def admin_page(request: Request, _: bool = Depends(require_admin)) -> HTMLResponse:
        from app.storage import GitHubStore

        saved = request.query_params.get("saved") == "1"
        err = request.query_params.get("err")
        if isinstance(runtime.store, GitHubStore):
            storage_note = "💾 Speicherung: <b>GitHub</b> – Änderungen sind dauerhaft (als Commit)."
        else:
            storage_note = (
                "⚠️ Speicherung: <b>lokal</b> – auf Render Free gehen Änderungen bei "
                "Neustart verloren. Für dauerhaftes Speichern GitHub einrichten (siehe docs/ADMIN.md)."
            )
        return HTMLResponse(_render_page(runtime.directory, saved, storage_note, err))

    @router.post("")
    async def admin_save(request: Request, _: bool = Depends(require_admin)) -> RedirectResponse:
        from urllib.parse import quote

        form = await request.form()
        directory = _parse_form(form)
        # In Thread auslagern: store.save kann (bei GitHub) blockierend HTTP machen
        # und würde sonst den Event-Loop und damit laufende Anrufe einfrieren.
        try:
            await asyncio.to_thread(runtime.save_directory, directory)
            return RedirectResponse(url="/admin?saved=1", status_code=status.HTTP_303_SEE_OTHER)
        except Exception as exc:  # noqa: BLE001 - Persistierung fehlgeschlagen
            logging.getLogger(__name__).exception("Speichern der Konfiguration fehlgeschlagen")
            # Änderung ist bereits live (apply_directory lief vor dem Store-Write).
            msg = quote(f"Live übernommen, aber Speichern fehlgeschlagen: {str(exc)[:160]}")
            return RedirectResponse(url=f"/admin?err={msg}", status_code=status.HTTP_303_SEE_OTHER)

    @router.get("/status", response_class=HTMLResponse)
    async def admin_status(request: Request, _: bool = Depends(require_admin)) -> HTMLResponse:
        from app.diagnostics import run_checks

        checks = await run_checks(settings, runtime.directory)
        mail_msg = request.query_params.get("mail")
        return HTMLResponse(_render_status(checks, settings, mail_msg))

    @router.post("/test-email")
    async def admin_test_email(request: Request, _: bool = Depends(require_admin)) -> RedirectResponse:
        from urllib.parse import quote

        from app.notify.email import send_test_email

        form = await request.form()
        to_addr = (form.get("to") or settings.email_fallback_to or "").strip()
        ok, msg = await send_test_email(settings, to_addr)
        prefix = "✅ " if ok else "❌ "
        return RedirectResponse(
            url=f"/admin/status?mail={quote(prefix + msg)}",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    @router.get("/calls", response_class=HTMLResponse)
    async def admin_calls(request: Request, _: bool = Depends(require_admin)) -> HTMLResponse:
        return HTMLResponse(_render_calls(runtime.call_log.recent()))

    return router


def _parse_form(form) -> Directory:
    """Baut aus den Formulardaten ein Directory."""
    # Geschäftszeiten
    bh_kwargs = {"timezone": (form.get("timezone") or "Europe/Berlin").strip()}
    for key, _label in _WEEKDAYS:
        open_t = (form.get(f"{key}_open") or "").strip()
        close_t = (form.get(f"{key}_close") or "").strip()
        bh_kwargs[key] = [open_t, close_t] if open_t and close_t else []

    # Abteilungen
    departments = []
    count = int(form.get("dept_count") or 0)
    for i in range(count):
        name = (form.get(f"dept_{i}_name") or "").strip()
        email = (form.get(f"dept_{i}_email") or "").strip()
        if not name and not email:
            continue  # leere/gelöschte Zeile
        dept_id = (form.get(f"dept_{i}_id") or "").strip() or _slugify(name)
        topics = (form.get(f"dept_{i}_topics") or "").strip()
        departments.append(
            Department(
                id=dept_id,
                name=name or dept_id,
                topics=[topics] if topics else [],
                email=email,
                phone=(form.get(f"dept_{i}_phone") or "").strip(),
                transfer_enabled=form.get(f"dept_{i}_transfer") == "on",
            )
        )

    fallback = Fallback(
        department_name=(form.get("fallback_name") or "Zentrale").strip(),
        email=(form.get("fallback_email") or "").strip(),
        phone=(form.get("fallback_phone") or "").strip(),
        transfer_enabled=form.get("fallback_transfer") == "on",
    )

    return Directory(
        company_name=(form.get("company_name") or "Unternehmen").strip(),
        greeting=(form.get("greeting") or "").strip(),
        business_hours=BusinessHours(**bh_kwargs),
        departments=departments,
        fallback=fallback,
    )


# --- HTML-Rendering ----------------------------------------------------------
def _dept_row(i, d: Department | None = None) -> str:
    did = _esc(d.id) if d else ""
    name = _esc(d.name) if d else ""
    topics = _esc("; ".join(d.topics)) if d else ""
    email = _esc(d.email) if d else ""
    phone = _esc(d.phone) if d else ""
    checked = "checked" if (d and d.transfer_enabled) else ""
    return f"""
    <div class="dept">
      <div class="grid">
        <label>Kürzel/ID<input name="dept_{i}_id" value="{did}" placeholder="z.B. vertrieb"></label>
        <label>Name<input name="dept_{i}_name" value="{name}" placeholder="z.B. Vertrieb"></label>
        <label>E-Mail<input name="dept_{i}_email" type="email" value="{email}" placeholder="vertrieb@firma.de"></label>
        <label>Telefon (Weiterleitung)<input name="dept_{i}_phone" value="{phone}" placeholder="+49..."></label>
      </div>
      <label>Themen/Stichworte (wofür zuständig?)
        <input name="dept_{i}_topics" value="{topics}" placeholder="Angebote, Bestellungen, Preise">
      </label>
      <label class="check"><input type="checkbox" name="dept_{i}_transfer" {checked}> Anruf direkt durchstellen</label>
    </div>
    """


def _render_page(directory: Directory, saved: bool, storage_note: str = "", err: str | None = None) -> str:
    bh = directory.business_hours
    days_html = ""
    for key, label in _WEEKDAYS:
        window = getattr(bh, key)
        open_v = window[0] if window else ""
        close_v = window[1] if window else ""
        days_html += f"""
        <div class="day">
          <span>{label}</span>
          <input name="{key}_open" value="{open_v}" placeholder="08:00">
          <input name="{key}_close" value="{close_v}" placeholder="17:00">
        </div>"""

    depts_html = "".join(_dept_row(i, d) for i, d in enumerate(directory.departments))
    next_index = len(directory.departments)
    # Vorlage für neue Zeilen: eindeutiger Platzhalter, in JS durch Index ersetzt.
    template_row = _dept_row("ROWIDX")

    banner = (
        '<div class="ok">✅ Gespeichert – Änderungen sind sofort aktiv.</div>' if saved else ""
    )
    if err:
        banner += f'<div class="err">⚠️ {_esc(err)}</div>'

    return f"""<!doctype html>
<html lang="de"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Call-Agent – Konfiguration</title>
<style>
  body {{ font-family: system-ui, sans-serif; max-width: 860px; margin: 0 auto; padding: 24px; color:#1a1a1a; background:#f7f7f8; }}
  h1 {{ font-size: 1.4rem; }} h2 {{ font-size: 1.1rem; margin-top: 28px; }}
  fieldset {{ border:1px solid #ddd; border-radius:10px; padding:16px; margin-bottom:18px; background:#fff; }}
  legend {{ font-weight:600; padding:0 6px; }}
  label {{ display:block; font-size:.85rem; color:#444; margin:8px 0; }}
  input, textarea {{ width:100%; padding:8px; border:1px solid #ccc; border-radius:7px; font-size:.95rem; box-sizing:border-box; }}
  textarea {{ min-height:60px; }}
  .grid {{ display:grid; grid-template-columns:1fr 1fr; gap:10px; }}
  .dept {{ border:1px solid #e3e3e3; border-radius:10px; padding:12px; margin-bottom:12px; background:#fafafa; }}
  .day {{ display:grid; grid-template-columns:120px 1fr 1fr; gap:10px; align-items:center; margin-bottom:6px; }}
  .check {{ display:flex; align-items:center; gap:8px; }} .check input {{ width:auto; }}
  button {{ background:#2d6cdf; color:#fff; border:0; padding:11px 18px; border-radius:8px; font-size:1rem; cursor:pointer; }}
  button.secondary {{ background:#666; }}
  .ok {{ background:#e6f7ec; border:1px solid #93d6ab; padding:10px 14px; border-radius:8px; margin-bottom:16px; }}
  .err {{ background:#fdecea; border:1px solid #e0a0a0; padding:10px 14px; border-radius:8px; margin-bottom:16px; }}
  .hint {{ color:#666; font-size:.82rem; }}
</style></head>
<body>
  <h1>📞 Call-Agent – Konfiguration</h1>
  <p><a href="/admin/status">🔎 Selbsttest & Status</a> &nbsp;·&nbsp; <a href="/admin/calls">📋 Anruf-Protokoll</a></p>
  <p class="hint">{storage_note}</p>
  {banner}
  <form method="post" action="/admin">
    <fieldset>
      <legend>Unternehmen</legend>
      <label>Firmenname<input name="company_name" value="{_esc(directory.company_name)}"></label>
      <label>Begrüßung (was der Agent zu Beginn sagt)
        <textarea name="greeting">{_esc(directory.greeting)}</textarea>
      </label>
    </fieldset>

    <fieldset>
      <legend>Geschäftszeiten</legend>
      <label>Zeitzone<input name="timezone" value="{_esc(bh.timezone)}"></label>
      <p class="hint">Leer lassen = an diesem Tag geschlossen. Außerhalb der Zeiten wird nicht durchgestellt, sondern eine Nachricht aufgenommen.</p>
      {days_html}
    </fieldset>

    <fieldset>
      <legend>Abteilungen / Ansprechpartner</legend>
      <div id="depts">{depts_html}</div>
      <button type="button" class="secondary" onclick="addDept()">+ Abteilung hinzufügen</button>
      <input type="hidden" name="dept_count" id="dept_count" value="{next_index}">
    </fieldset>

    <fieldset>
      <legend>Fallback (wenn nichts passt)</legend>
      <div class="grid">
        <label>Bezeichnung<input name="fallback_name" value="{_esc(directory.fallback.department_name)}"></label>
        <label>E-Mail<input name="fallback_email" type="email" value="{_esc(directory.fallback.email)}"></label>
        <label>Telefon<input name="fallback_phone" value="{_esc(directory.fallback.phone)}"></label>
      </div>
      <label class="check"><input type="checkbox" name="fallback_transfer" {"checked" if directory.fallback.transfer_enabled else ""}> Durchstellen erlaubt</label>
    </fieldset>

    <button type="submit">💾 Speichern</button>
  </form>

  <script>
    var tpl = {template_row!r};
    function addDept() {{
      var c = document.getElementById('dept_count');
      var i = parseInt(c.value, 10);
      var html = tpl.replaceAll('ROWIDX', i);
      var div = document.createElement('div');
      div.innerHTML = html;
      document.getElementById('depts').appendChild(div.firstElementChild || div);
      c.value = i + 1;
    }}
  </script>
</body></html>"""


def _render_status(checks, settings, mail_msg: str | None) -> str:
    """Rendert das Selbsttest-Dashboard mit Live-Status der Dienste."""
    icons = {"ok": "✅", "warn": "⚠️", "fail": "❌"}
    rows = ""
    for c in checks:
        rows += (
            f'<tr><td>{icons.get(c.status, "•")}</td>'
            f"<td><b>{_esc(c.name)}</b></td>"
            f"<td>{_esc(c.detail)}</td></tr>"
        )

    all_ok = all(c.status == "ok" for c in checks)
    summary = (
        '<div class="ok">🎉 Alle geprüften Dienste laufen!</div>'
        if all_ok
        else '<div class="hint">Behebe die mit ❌ markierten Punkte. ⚠️ = vorübergehend/Hinweis.</div>'
    )
    mail_banner = f'<div class="ok">{_esc(mail_msg)}</div>' if mail_msg else ""
    to_default = _esc(settings.email_fallback_to)

    return f"""<!doctype html>
<html lang="de"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Call-Agent – Selbsttest</title>
<style>
  body {{ font-family: system-ui, sans-serif; max-width: 760px; margin: 0 auto; padding: 24px; color:#1a1a1a; background:#f7f7f8; }}
  h1 {{ font-size: 1.4rem; }}
  table {{ width:100%; border-collapse:collapse; background:#fff; border-radius:10px; overflow:hidden; }}
  td {{ padding:12px 10px; border-bottom:1px solid #eee; vertical-align:top; }}
  td:first-child {{ width:34px; font-size:1.1rem; text-align:center; }}
  fieldset {{ border:1px solid #ddd; border-radius:10px; padding:16px; margin:18px 0; background:#fff; }}
  legend {{ font-weight:600; padding:0 6px; }}
  input {{ padding:8px; border:1px solid #ccc; border-radius:7px; font-size:.95rem; }}
  button {{ background:#2d6cdf; color:#fff; border:0; padding:10px 16px; border-radius:8px; font-size:1rem; cursor:pointer; }}
  .ok {{ background:#e6f7ec; border:1px solid #93d6ab; padding:10px 14px; border-radius:8px; margin:14px 0; }}
  .hint {{ color:#666; font-size:.85rem; margin:14px 0; }}
  a {{ color:#2d6cdf; }}
</style></head>
<body>
  <h1>🔎 Selbsttest & Status</h1>
  <p><a href="/admin">← zurück zur Konfiguration</a></p>
  {mail_banner}
  {summary}
  <table>{rows}</table>

  <fieldset>
    <legend>📧 Test-E-Mail senden</legend>
    <p class="hint">Sendet eine Test-Mail über die aktuelle SMTP-Konfiguration – ohne Anruf.</p>
    <form method="post" action="/admin/test-email">
      <input name="to" type="email" value="{to_default}" placeholder="empfaenger@firma.de" size="32">
      <button type="submit">Test-E-Mail senden</button>
    </form>
  </fieldset>

  <p><a href="/admin/status">🔄 Status neu prüfen</a></p>
</body></html>"""


def _render_calls(records) -> str:
    """Rendert die letzten Anrufe/Zusammenfassungen."""
    if records:
        rows = ""
        for r in records:
            when = r.time.strftime("%d.%m. %H:%M")
            mail = "📧" if r.emailed else "—"
            transferred = "↪️ durchgestellt" if r.transferred else ""
            urgency = {"hoch": "🔴", "normal": "", "niedrig": ""}.get(r.urgency, "")
            rows += f"""
            <div class="call">
              <div class="meta">{when} · <b>{_esc(r.department)}</b> · {_esc(r.caller)} {urgency} {transferred} · Mail: {mail}</div>
              <div class="subj">{_esc(r.subject)}</div>
              <div class="body">{_esc(r.summary)}</div>
              <div class="req"><b>Anliegen:</b> {_esc(r.request)}</div>
            </div>"""
        body = rows
    else:
        body = '<p class="hint">Noch keine Anrufe protokolliert. Nach dem nächsten Anruf erscheint hier die Zusammenfassung.</p>'

    return f"""<!doctype html>
<html lang="de"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Call-Agent – Anruf-Protokoll</title>
<style>
  body {{ font-family: system-ui, sans-serif; max-width: 820px; margin: 0 auto; padding: 24px; color:#1a1a1a; background:#f7f7f8; }}
  h1 {{ font-size: 1.4rem; }}
  .call {{ background:#fff; border:1px solid #e3e3e3; border-radius:10px; padding:14px 16px; margin-bottom:12px; }}
  .meta {{ color:#666; font-size:.82rem; margin-bottom:6px; }}
  .subj {{ font-weight:600; margin-bottom:4px; }}
  .body {{ margin-bottom:6px; }}
  .req {{ font-size:.9rem; color:#333; }}
  .hint {{ color:#666; }}
  a {{ color:#2d6cdf; }}
</style></head>
<body>
  <h1>📋 Anruf-Protokoll <span style="font-size:.8rem;color:#888">(letzte {len(records)})</span></h1>
  <p><a href="/admin">← zurück</a> &nbsp;·&nbsp; <a href="/admin/calls">🔄 aktualisieren</a></p>
  {body}
  <p class="hint">Hinweis: flüchtige Liste (im Speicher). Überlebt keinen Neustart.</p>
</body></html>"""
