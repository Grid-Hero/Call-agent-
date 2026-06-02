"""Tests für das Speichern des Verzeichnisses und die Admin-Oberfläche."""

from __future__ import annotations

import shutil

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.admin import create_admin_router
from app.config import Settings
from app.directory import load_directory, save_directory
from app.runtime import Runtime


def _settings(tmp_path, password=""):
    p = tmp_path / "directory.yaml"
    shutil.copy("config/directory.yaml", p)
    return Settings(
        directory_path=str(p),
        admin_password=password,
        anthropic_api_key="x",
        twilio_validate_signature=False,
    )


def test_save_directory_roundtrip(tmp_path):
    p = tmp_path / "dir.yaml"
    shutil.copy("config/directory.yaml", p)
    d = load_directory(str(p))
    d.company_name = "Planet in Green"
    save_directory(d, str(p))
    reloaded = load_directory(str(p))
    assert reloaded.company_name == "Planet in Green"
    assert len(reloaded.departments) == len(d.departments)


def _client(settings):
    rt = Runtime(settings)
    app = FastAPI()
    app.include_router(create_admin_router(rt))
    return TestClient(app), rt


def test_admin_disabled_without_password(tmp_path):
    client, _ = _client(_settings(tmp_path, password=""))
    assert client.get("/admin").status_code == 503


def test_admin_requires_auth(tmp_path):
    client, _ = _client(_settings(tmp_path, password="geheim"))
    assert client.get("/admin").status_code == 401


def test_admin_page_loads_with_auth(tmp_path):
    client, _ = _client(_settings(tmp_path, password="geheim"))
    r = client.get("/admin", auth=("admin", "geheim"))
    assert r.status_code == 200
    assert "Konfiguration" in r.text


def test_admin_save_updates_directory(tmp_path):
    settings = _settings(tmp_path, password="geheim")
    client, rt = _client(settings)
    r = client.post(
        "/admin",
        auth=("admin", "geheim"),
        data={
            "company_name": "Planet in Green",
            "greeting": "Hallo!",
            "timezone": "Europe/Berlin",
            "monday_open": "08:00",
            "monday_close": "17:00",
            "dept_count": "1",
            "dept_0_id": "vertrieb",
            "dept_0_name": "Vertrieb",
            "dept_0_email": "vertrieb@planet-in-green.de",
            "dept_0_phone": "+49301234567",
            "dept_0_topics": "Angebote, Bestellungen",
            "dept_0_transfer": "on",
            "fallback_name": "Zentrale",
            "fallback_email": "info@planet-in-green.de",
            "fallback_phone": "+49301234560",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303
    # Runtime wurde live neu geladen.
    assert rt.directory.company_name == "Planet in Green"
    assert len(rt.directory.departments) == 1
    dept = rt.directory.departments[0]
    assert dept.email == "vertrieb@planet-in-green.de"
    assert dept.transfer_enabled is True
    assert rt.directory.business_hours.monday == ["08:00", "17:00"]


def test_status_requires_auth(tmp_path):
    client, _ = _client(_settings(tmp_path, password="geheim"))
    assert client.get("/admin/status").status_code == 401


def test_status_page_renders(tmp_path, monkeypatch):
    import app.diagnostics as diag

    async def fake_run_checks(s, directory=None):
        return [
            diag.Check("Claude (KI)", "ok", "Modell x"),
            diag.Check("E-Mail (SMTP)", "fail", "kein Host"),
        ]

    monkeypatch.setattr(diag, "run_checks", fake_run_checks)
    client, _ = _client(_settings(tmp_path, password="geheim"))
    r = client.get("/admin/status", auth=("admin", "geheim"))
    assert r.status_code == 200
    assert "Selbsttest" in r.text
    assert "Claude (KI)" in r.text


def test_test_email_requires_auth(tmp_path):
    client, _ = _client(_settings(tmp_path, password="geheim"))
    assert client.post("/admin/test-email", data={"to": "x@y.de"}).status_code == 401


def test_test_email_without_smtp_reports_failure(tmp_path):
    # _settings hat keinen SMTP_HOST -> Test-Mail schlägt sofort (ohne Netzwerk) fehl
    client, _ = _client(_settings(tmp_path, password="geheim"))
    r = client.post(
        "/admin/test-email", auth=("admin", "geheim"),
        data={"to": "x@y.de"}, follow_redirects=False,
    )
    assert r.status_code == 303
    assert "/admin/status" in r.headers["location"]


def test_is_demo_email():
    from app.directory import is_demo_email

    assert is_demo_email("vertrieb@example.com")
    assert is_demo_email("")
    assert not is_demo_email("schmidt@planetingreen.de")


@pytest.mark.asyncio
async def test_finalize_routes_demo_email_to_fallback(tmp_path, monkeypatch):
    import app.finalize as fin
    from app.directory import load_directory

    captured = {}

    async def fake_send(summary, session, settings, to_addr):
        captured["to"] = to_addr
        return True

    monkeypatch.setattr(fin, "send_summary", fake_send)

    s = _settings(tmp_path)
    s = s.model_copy(update={"email_fallback_to": "echt@planetingreen.de"})
    directory = load_directory(str(tmp_path / "directory.yaml"))

    class _Agent:
        async def summarize(self, session):
            from app.models import CallSummary
            return CallSummary(
                caller_number="+49", department_id="vertrieb",
                department_name="Vertrieb", subject="x", summary="y", caller_request="z",
            )

    from app.models import CallSession
    sess = CallSession(call_sid="C", caller_number="+49", department_id="vertrieb")
    await fin.finish_with_message(_Agent(), directory, s, sess)
    # vertrieb hat @example.com -> echte Fallback-Adresse wird verwendet
    assert captured["to"] == "echt@planetingreen.de"


def test_call_log_records_and_renders(tmp_path):
    from app.call_log import CallLog
    from app.models import CallSession, CallSummary

    log = CallLog()
    summ = CallSummary(
        caller_number="+4915100", department_id="vertrieb", department_name="Vertrieb",
        subject="Angebot", summary="Kunde will Angebot", caller_request="Bitte Angebot zusenden",
        urgency="hoch",
    )
    sess = CallSession(call_sid="C1", caller_number="+4915100")
    log.add(summ, sess, emailed=True)
    recent = log.recent()
    assert len(recent) == 1 and recent[0].subject == "Angebot"


def test_calls_page_requires_auth_and_renders(tmp_path):
    client, rt = _client(_settings(tmp_path, password="geheim"))
    assert client.get("/admin/calls").status_code == 401
    r = client.get("/admin/calls", auth=("admin", "geheim"))
    assert r.status_code == 200
    assert "Anruf-Protokoll" in r.text


@pytest.mark.asyncio
async def test_email_provider_brevo_dispatch(monkeypatch):
    import app.notify.email as email
    from app.config import Settings

    captured = {}

    async def fake_brevo(settings, to_addr, subject, body):
        captured["called"] = True
        return True, "gesendet (Brevo-API)"

    monkeypatch.setattr(email, "_deliver_brevo", fake_brevo)
    s = Settings(email_provider="brevo", brevo_api_key="key", email_from="a@b.de")
    ok, msg = await email.send_test_email(s, "x@y.de")
    assert ok and captured.get("called") is True


@pytest.mark.asyncio
async def test_email_brevo_without_key_reports_failure():
    import app.notify.email as email
    from app.config import Settings

    s = Settings(email_provider="brevo", brevo_api_key="", email_from="a@b.de")
    ok, msg = await email.send_test_email(s, "x@y.de")
    assert not ok and "BREVO_API_KEY" in msg
