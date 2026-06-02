"""Passwortgeschützte Admin-Weboberfläche zum Konfigurieren des Verzeichnisses.

Erreichbar unter ``/admin`` (HTTP-Basic-Auth). Bearbeitet Firmenname,
Begrüßung, Geschäftszeiten und Abteilungen und schreibt sie nach
``directory.yaml`` zurück; danach lädt die Runtime live neu.
"""

from __future__ import annotations

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
    save_directory,
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
        saved = request.query_params.get("saved") == "1"
        return HTMLResponse(_render_page(runtime.directory, saved))

    @router.post("")
    async def admin_save(request: Request, _: bool = Depends(require_admin)) -> RedirectResponse:
        form = await request.form()
        directory = _parse_form(form)
        save_directory(directory, settings.directory_path)
        runtime.reload()
        return RedirectResponse(url="/admin?saved=1", status_code=status.HTTP_303_SEE_OTHER)

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


def _render_page(directory: Directory, saved: bool) -> str:
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
  .hint {{ color:#666; font-size:.82rem; }}
</style></head>
<body>
  <h1>📞 Call-Agent – Konfiguration</h1>
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
