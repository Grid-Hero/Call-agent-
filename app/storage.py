"""Speicher-Backends für die Verzeichnis-Konfiguration.

- LocalFileStore: liest/schreibt die YAML-Datei lokal (Standard).
- GitHubStore: liest/schreibt die YAML-Datei direkt im GitHub-Repo (als Commit).
  So bleiben über /admin gemachte Änderungen dauerhaft erhalten – auch auf
  Renders flüchtigem Dateisystem – und sind zugleich versioniert.
"""

from __future__ import annotations

import base64
import logging
from abc import ABC, abstractmethod
from pathlib import Path

import httpx

from app.config import Settings

logger = logging.getLogger(__name__)

_GITHUB_API = "https://api.github.com"


class DirectoryStore(ABC):
    @abstractmethod
    def load(self) -> str:
        """Gibt den YAML-Text der Konfiguration zurück."""

    @abstractmethod
    def save(self, text: str, message: str = "Konfiguration aktualisiert") -> None:
        """Speichert den YAML-Text dauerhaft."""


class LocalFileStore(DirectoryStore):
    def __init__(self, path: str) -> None:
        self.path = path

    def load(self) -> str:
        return Path(self.path).read_text(encoding="utf-8")

    def save(self, text: str, message: str = "Konfiguration aktualisiert") -> None:
        Path(self.path).write_text(text, encoding="utf-8")


class GitHubStore(DirectoryStore):
    """Liest/schreibt die Konfig über die GitHub Contents API.

    Fällt beim Laden auf die lokale Datei zurück, falls GitHub nicht erreichbar
    ist (z.B. beim allerersten Start). Beim Speichern wird zusätzlich die lokale
    Datei aktualisiert, damit die laufende Instanz konsistent bleibt.
    """

    def __init__(self, settings: Settings, local_fallback: str) -> None:
        self.repo = settings.github_repo
        self.branch = settings.github_branch
        self.path = settings.github_config_path
        self.token = settings.github_token
        self.local_fallback = local_fallback
        self._sha: str | None = None

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def _contents_url(self) -> str:
        return f"{_GITHUB_API}/repos/{self.repo}/contents/{self.path}"

    def load(self) -> str:
        try:
            r = httpx.get(
                self._contents_url(),
                headers=self._headers(),
                params={"ref": self.branch},
                timeout=15,
            )
            r.raise_for_status()
            data = r.json()
            self._sha = data.get("sha")
            text = base64.b64decode(data["content"]).decode("utf-8")
            logger.info("Konfiguration aus GitHub geladen (%s@%s)", self.path, self.branch)
            return text
        except Exception:  # pragma: no cover - Netzwerk
            logger.exception("GitHub-Load fehlgeschlagen – nutze lokale Datei")
            return Path(self.local_fallback).read_text(encoding="utf-8")

    def save(self, text: str, message: str = "Konfiguration via /admin aktualisiert") -> None:
        # Aktuelle SHA holen (für Update nötig), falls noch nicht bekannt.
        if self._sha is None:
            try:
                r = httpx.get(
                    self._contents_url(),
                    headers=self._headers(),
                    params={"ref": self.branch},
                    timeout=15,
                )
                if r.status_code == 200:
                    self._sha = r.json().get("sha")
            except Exception:  # pragma: no cover
                logger.exception("SHA-Abfrage fehlgeschlagen")

        def _put(sha: str | None):
            body = {
                "message": message,
                "content": base64.b64encode(text.encode("utf-8")).decode("ascii"),
                "branch": self.branch,
            }
            if sha:
                body["sha"] = sha
            return httpx.put(self._contents_url(), headers=self._headers(), json=body, timeout=20)

        r = _put(self._sha)
        # SHA veraltet/Konflikt (z.B. zwischenzeitlicher Commit) -> frische SHA holen, einmal erneut.
        if r.status_code in (409, 422):
            logger.warning("GitHub-Commit SHA-Konflikt – hole aktuelle SHA und versuche erneut")
            try:
                g = httpx.get(
                    self._contents_url(), headers=self._headers(),
                    params={"ref": self.branch}, timeout=15,
                )
                self._sha = g.json().get("sha") if g.status_code == 200 else None
            except Exception:  # pragma: no cover
                self._sha = None
            r = _put(self._sha)
        r.raise_for_status()
        self._sha = r.json()["content"]["sha"]
        logger.info("Konfiguration nach GitHub committet (%s@%s)", self.path, self.branch)

        # Lokale Datei mitziehen, damit die laufende Instanz konsistent ist.
        try:
            Path(self.local_fallback).write_text(text, encoding="utf-8")
        except Exception:  # pragma: no cover
            pass


def build_store(settings: Settings) -> DirectoryStore:
    """Wählt das Speicher-Backend anhand der Konfiguration."""
    if settings.github_token and settings.github_repo:
        logger.info("Konfig-Speicher: GitHub (%s)", settings.github_repo)
        return GitHubStore(settings, settings.directory_path)
    return LocalFileStore(settings.directory_path)
