"""Tests für das Speichern des Verzeichnisses und die Admin-Oberfläche."""

from __future__ import annotations

import shutil

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
