"""Tests für die Speicher-Backends (lokale Datei und GitHub)."""

from __future__ import annotations

import base64

import pytest

from app.config import Settings
from app.storage import GitHubStore, LocalFileStore, build_store


def test_build_store_local_without_github(tmp_path):
    s = Settings(directory_path=str(tmp_path / "d.yaml"))
    assert isinstance(build_store(s), LocalFileStore)


def test_build_store_github_when_configured(tmp_path):
    s = Settings(
        directory_path=str(tmp_path / "d.yaml"),
        github_token="tok",
        github_repo="owner/repo",
    )
    assert isinstance(build_store(s), GitHubStore)


def test_local_store_roundtrip(tmp_path):
    p = tmp_path / "d.yaml"
    store = LocalFileStore(str(p))
    store.save("hello: world\n")
    assert store.load() == "hello: world\n"


class _Resp:
    def __init__(self, status=200, payload=None):
        self.status_code = status
        self._payload = payload or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


def _github_settings(tmp_path):
    p = tmp_path / "d.yaml"
    p.write_text("local: fallback\n", encoding="utf-8")
    return Settings(
        directory_path=str(p),
        github_token="tok",
        github_repo="owner/repo",
        github_branch="main",
        github_config_path="config/directory.yaml",
    )


def test_github_store_load(tmp_path, monkeypatch):
    text = "company:\n  name: GitHub Co\n"
    payload = {"sha": "abc123", "content": base64.b64encode(text.encode()).decode()}
    monkeypatch.setattr("app.storage.httpx.get", lambda *a, **k: _Resp(200, payload))

    store = GitHubStore(_github_settings(tmp_path), str(tmp_path / "d.yaml"))
    assert store.load() == text
    assert store._sha == "abc123"


def test_github_store_load_falls_back_to_local(tmp_path, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("network down")

    monkeypatch.setattr("app.storage.httpx.get", boom)
    store = GitHubStore(_github_settings(tmp_path), str(tmp_path / "d.yaml"))
    assert store.load() == "local: fallback\n"


def test_github_store_save_commits(tmp_path, monkeypatch):
    captured = {}

    def fake_put(url, headers=None, json=None, timeout=None):
        captured["url"] = url
        captured["body"] = json
        return _Resp(200, {"content": {"sha": "newsha"}})

    monkeypatch.setattr("app.storage.httpx.put", fake_put)

    store = GitHubStore(_github_settings(tmp_path), str(tmp_path / "d.yaml"))
    store._sha = "oldsha"  # vermeidet zusätzlichen GET
    store.save("company:\n  name: Neu\n", message="Test")

    assert "owner/repo" in captured["url"]
    assert captured["body"]["sha"] == "oldsha"
    assert captured["body"]["branch"] == "main"
    decoded = base64.b64decode(captured["body"]["content"]).decode()
    assert "Neu" in decoded
    assert store._sha == "newsha"
    # Lokale Datei wurde mitgezogen.
    assert "Neu" in (tmp_path / "d.yaml").read_text()
