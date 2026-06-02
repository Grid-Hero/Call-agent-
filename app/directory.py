"""Lädt das Mitarbeiter-/Abteilungsverzeichnis aus der YAML-Konfiguration."""

from __future__ import annotations

from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

import yaml
from pydantic import BaseModel


class Department(BaseModel):
    id: str
    name: str
    topics: list[str] = []
    email: str
    phone: str = ""
    transfer_enabled: bool = False


class Fallback(BaseModel):
    department_name: str = "Zentrale"
    email: str
    phone: str = ""
    transfer_enabled: bool = False


class BusinessHours(BaseModel):
    timezone: str = "Europe/Berlin"
    monday: list[str] = []
    tuesday: list[str] = []
    wednesday: list[str] = []
    thursday: list[str] = []
    friday: list[str] = []
    saturday: list[str] = []
    sunday: list[str] = []

    _WEEKDAYS = (
        "monday",
        "tuesday",
        "wednesday",
        "thursday",
        "friday",
        "saturday",
        "sunday",
    )

    def is_open(self, now: Optional[datetime] = None) -> bool:
        """Prüft, ob aktuell innerhalb der Geschäftszeiten."""
        tz = ZoneInfo(self.timezone)
        now = now.astimezone(tz) if now else datetime.now(tz)
        window = getattr(self, self._WEEKDAYS[now.weekday()])
        if not window:
            return False
        start_str, end_str = window
        start = now.replace(
            hour=int(start_str[:2]), minute=int(start_str[3:]), second=0, microsecond=0
        )
        end = now.replace(
            hour=int(end_str[:2]), minute=int(end_str[3:]), second=0, microsecond=0
        )
        return start <= now <= end


class Directory(BaseModel):
    company_name: str
    greeting: str
    business_hours: BusinessHours
    departments: list[Department]
    fallback: Fallback

    def get(self, department_id: Optional[str]) -> Optional[Department]:
        if not department_id:
            return None
        return next((d for d in self.departments if d.id == department_id), None)

    def routing_target(self, department_id: Optional[str]) -> tuple[str, str, str, bool]:
        """Liefert (name, email, phone, transfer_enabled) – mit Fallback."""
        dept = self.get(department_id)
        if dept:
            return dept.name, dept.email, dept.phone, dept.transfer_enabled
        return (
            self.fallback.department_name,
            self.fallback.email,
            self.fallback.phone,
            self.fallback.transfer_enabled,
        )


def load_directory(path: str) -> Directory:
    """Lädt und validiert die YAML-Verzeichnisdatei von einem Pfad."""
    return parse_directory_yaml(Path(path).read_text(encoding="utf-8"))


def parse_directory_yaml(text: str) -> Directory:
    """Parst YAML-Text zu einem Directory."""
    raw = yaml.safe_load(text)
    company = raw.get("company", {})
    return Directory(
        company_name=company.get("name", "Unternehmen"),
        greeting=company.get("greeting", "Guten Tag, wie kann ich helfen?").strip(),
        business_hours=BusinessHours(**company.get("business_hours", {})),
        departments=[Department(**d) for d in raw.get("departments", [])],
        fallback=Fallback(**raw["fallback"]),
    )


@lru_cache
def get_directory(path: str) -> Directory:
    return load_directory(path)


_WEEKDAYS = (
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
)


_DEMO_PHONE_PREFIXES = ("+49301111", "+49302222", "+49303333", "+49304444", "+49300000")


def is_demo_phone(phone: str) -> bool:
    """True für leere oder offensichtliche Platzhalter-/Demo-Telefonnummern."""
    phone = (phone or "").strip()
    return not phone or any(phone.startswith(p) for p in _DEMO_PHONE_PREFIXES)


def directory_to_dict(directory: Directory) -> dict:
    """Wandelt ein Directory zurück in die YAML-Struktur (für Speichern/Anzeige)."""
    bh = {"timezone": directory.business_hours.timezone}
    for day in _WEEKDAYS:
        bh[day] = list(getattr(directory.business_hours, day))
    return {
        "company": {
            "name": directory.company_name,
            "greeting": directory.greeting,
            "business_hours": bh,
        },
        "departments": [
            {
                "id": d.id,
                "name": d.name,
                "topics": list(d.topics),
                "email": d.email,
                "phone": d.phone,
                "transfer_enabled": d.transfer_enabled,
            }
            for d in directory.departments
        ],
        "fallback": {
            "department_name": directory.fallback.department_name,
            "email": directory.fallback.email,
            "phone": directory.fallback.phone,
            "transfer_enabled": directory.fallback.transfer_enabled,
        },
    }


def directory_to_yaml(directory: Directory) -> str:
    """Serialisiert ein Directory als YAML-Text."""
    return yaml.safe_dump(
        directory_to_dict(directory), allow_unicode=True, sort_keys=False
    )


def save_directory(directory: Directory, path: str) -> None:
    """Schreibt das Verzeichnis als YAML in eine Datei und leert den Cache."""
    Path(path).write_text(directory_to_yaml(directory), encoding="utf-8")
    get_directory.cache_clear()
