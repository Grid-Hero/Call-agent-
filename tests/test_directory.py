"""Tests für das Verzeichnis und die Geschäftszeiten."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from app.directory import BusinessHours


def test_directory_loads(directory):
    assert directory.company_name
    assert len(directory.departments) >= 1
    assert directory.fallback.email


def test_routing_target_known(directory):
    name, email, phone, transfer = directory.routing_target("support")
    assert name == "Technischer Support"
    assert email == "support@example.com"
    assert transfer is True


def test_routing_target_fallback(directory):
    name, email, _phone, transfer = directory.routing_target("gibt-es-nicht")
    assert name == directory.fallback.department_name
    assert email == directory.fallback.email


def test_business_hours_open_and_closed():
    bh = BusinessHours(timezone="Europe/Berlin", monday=["08:00", "17:00"])
    tz = ZoneInfo("Europe/Berlin")
    # Montag 10:00 -> offen
    assert bh.is_open(datetime(2026, 6, 1, 10, 0, tzinfo=tz)) is True
    # Montag 20:00 -> geschlossen
    assert bh.is_open(datetime(2026, 6, 1, 20, 0, tzinfo=tz)) is False
    # Sonntag -> kein Fenster -> geschlossen
    assert bh.is_open(datetime(2026, 5, 31, 10, 0, tzinfo=tz)) is False
