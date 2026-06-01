"""Zentrale Konfiguration, geladen aus Umgebungsvariablen (.env)."""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Alle Einstellungen des Call-Agents. Werte kommen aus der .env-Datei."""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # Anwendung
    app_base_url: str = "http://localhost:8000"
    app_env: str = "development"
    log_level: str = "INFO"

    # Telefonie
    telephony_provider: str = "twilio"
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_phone_number: str = ""
    twilio_validate_signature: bool = True

    # Anthropic / Claude
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-opus-4-8"
    agent_language: str = "de-DE"
    agent_company_name: str = "Musterfirma GmbH"

    # E-Mail
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_use_tls: bool = True
    email_from: str = ""
    email_fallback_to: str = ""

    # Verzeichnis
    directory_path: str = "config/directory.yaml"

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() == "production"


@lru_cache
def get_settings() -> Settings:
    """Gibt die (gecachte) Einstellungs-Instanz zurück."""
    return Settings()
