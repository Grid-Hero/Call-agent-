"""Gemeinsame Test-Fixtures."""

from __future__ import annotations

import pytest

from app.config import Settings
from app.directory import load_directory


@pytest.fixture
def settings() -> Settings:
    return Settings(
        app_base_url="https://test.example.com",
        telephony_provider="twilio",
        twilio_auth_token="test-token",
        twilio_validate_signature=False,
        twilio_phone_number="+4930000000",
        anthropic_api_key="test-key",
        agent_language="de-DE",
        smtp_host="",  # E-Mail-Versand im Test deaktiviert
        email_from="agent@example.com",
        email_fallback_to="zentrale@example.com",
        directory_path="config/directory.yaml",
    )


@pytest.fixture
def directory():
    return load_directory("config/directory.yaml")
