"""Claude-gestützte Gesprächslogik: Routing-Entscheidungen und Zusammenfassungen.

Verwendet die Anthropic-Messages-API mit Tool-Use (strukturierte Ausgabe) und
Prompt-Caching auf dem System-Prompt, da dieser über alle Anrufe konstant ist.
"""

from __future__ import annotations

import json
import logging

from anthropic import AsyncAnthropic

from app.config import Settings
from app.directory import Directory
from app.models import Action, CallSession, CallSummary, RoutingDecision, Speaker

logger = logging.getLogger(__name__)

# --- Tool-Definitionen (erzwingen strukturierte Ausgaben) --------------------

ROUTING_TOOL = {
    "name": "gespraech_steuern",
    "description": (
        "Entscheide nach der letzten Anrufer-Äußerung, wie das Gespräch "
        "weitergeführt wird, und formuliere die nächste Antwort des Agents."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["continue", "transfer", "message", "goodbye"],
                "description": (
                    "continue = Rückfrage stellen / mehr Infos sammeln; "
                    "transfer = an zuständige Abteilung durchstellen; "
                    "message = Anliegen ist klar, Nachricht aufnehmen und per "
                    "E-Mail weiterleiten; goodbye = kein echtes Anliegen / Spam."
                ),
            },
            "reply_text": {
                "type": "string",
                "description": "Was der Agent dem Anrufer als Nächstes sagt (gesprochene Sprache, freundlich, kurz).",
            },
            "department_id": {
                "type": "string",
                "description": "ID der zugeordneten Abteilung oder leer, wenn unklar.",
            },
            "reasoning": {
                "type": "string",
                "description": "Kurze interne Begründung der Entscheidung.",
            },
        },
        "required": ["action", "reply_text"],
    },
}

SUMMARY_TOOL = {
    "name": "zusammenfassung_erstellen",
    "description": "Fasse das Telefongespräch strukturiert für den zuständigen Mitarbeiter zusammen.",
    "input_schema": {
        "type": "object",
        "properties": {
            "subject": {"type": "string", "description": "Prägnante Betreffzeile (max. 80 Zeichen)."},
            "summary": {"type": "string", "description": "2–4 Sätze, worum es im Gespräch ging."},
            "caller_request": {"type": "string", "description": "Das konkrete Anliegen / die Bitte des Anrufers."},
            "callback_requested": {"type": "boolean", "description": "Wünscht der Anrufer einen Rückruf?"},
            "callback_number": {"type": "string", "description": "Genannte Rückrufnummer oder leer."},
            "urgency": {
                "type": "string",
                "enum": ["niedrig", "normal", "hoch"],
                "description": "Dringlichkeit des Anliegens.",
            },
        },
        "required": ["subject", "summary", "caller_request", "urgency"],
    },
}


def _build_system_prompt(directory: Directory, settings: Settings, is_open: bool) -> str:
    """Erzeugt den System-Prompt inkl. Abteilungsbeschreibung."""
    dept_lines = []
    for d in directory.departments:
        transfer = "durchstellbar" if d.transfer_enabled else "NICHT durchstellbar (nur Nachricht)"
        topics = "; ".join(d.topics)
        dept_lines.append(f"- id={d.id} | {d.name} | Themen: {topics} | {transfer}")
    departments_block = "\n".join(dept_lines)

    hours_note = (
        "Das Unternehmen hat aktuell GEÖFFNET – Weiterleitung ist möglich."
        if is_open
        else "Das Unternehmen ist aktuell GESCHLOSSEN – stelle NICHT durch, nimm immer eine Nachricht auf (action=message)."
    )

    return f"""Du bist der freundliche, professionelle Telefonassistent der {directory.company_name}.
Du nimmst eingehende Anrufe entgegen, verstehst das Anliegen und leitest es korrekt weiter.

Verfügbare Abteilungen:
{departments_block}

Regeln:
1. Sprich Deutsch, höflich, natürlich und KURZ (dies wird vorgelesen – keine Aufzählungen, keine Emojis, keine URLs).
2. Ermittle zuerst das Anliegen. Wenn es unklar ist, stelle EINE gezielte Rückfrage (action=continue).
3. Ordne das Anliegen einer Abteilung zu (department_id setzen).
4. Wenn die Abteilung durchstellbar ist und das Anliegen klar ist: action=transfer.
   Sage dem Anrufer freundlich, dass du verbindest.
5. Wenn die Abteilung NICHT durchstellbar ist oder das Unternehmen geschlossen hat:
   action=message. Frage nach Name und Rückrufnummer, falls noch nicht genannt, und
   sage zu, dass sich die zuständige Person meldet.
6. Bei eindeutigem Spam/Werbung oder keinem Anliegen: action=goodbye, höflich verabschieden.
7. Sei effizient: höchstens 1–2 Rückfragen, dann entscheide.

{hours_note}

Nutze IMMER das Tool 'gespraech_steuern' für deine Antwort."""


class CallAgent:
    """Kapselt die Claude-Aufrufe für einen Anruf."""

    def __init__(self, settings: Settings, directory: Directory):
        self.settings = settings
        self.directory = directory
        self.client = AsyncAnthropic(api_key=settings.anthropic_api_key)
        self.model = settings.anthropic_model

    def _messages(self, session: CallSession) -> list[dict]:
        """Wandelt den Gesprächsverlauf in Anthropic-Nachrichten um."""
        messages = []
        for turn in session.turns:
            role = "user" if turn.speaker == Speaker.CALLER else "assistant"
            messages.append({"role": role, "content": turn.text})
        # Die API erwartet, dass die letzte Nachricht vom 'user' stammt.
        if not messages or messages[-1]["role"] != "user":
            messages.append({"role": "user", "content": "(Anrufer schweigt)"})
        return messages

    async def decide(self, session: CallSession, is_open: bool) -> RoutingDecision:
        """Fragt Claude nach der nächsten Aktion."""
        system = [
            {
                "type": "text",
                "text": _build_system_prompt(self.directory, self.settings, is_open),
                "cache_control": {"type": "ephemeral"},  # System-Prompt cachen
            }
        ]
        try:
            response = await self.client.messages.create(
                model=self.model,
                max_tokens=1024,
                system=system,
                messages=self._messages(session),
                tools=[ROUTING_TOOL],
                tool_choice={"type": "tool", "name": "gespraech_steuern"},
            )
            payload = _extract_tool_input(response, "gespraech_steuern")
            return RoutingDecision(
                action=Action(payload["action"]),
                reply_text=payload["reply_text"],
                department_id=payload.get("department_id") or None,
                reasoning=payload.get("reasoning", ""),
            )
        except Exception:  # pragma: no cover - Laufzeit-Fallback
            logger.exception("Claude-Routing fehlgeschlagen – nutze Fallback (Nachricht)")
            return RoutingDecision(
                action=Action.MESSAGE,
                reply_text=(
                    "Entschuldigung, ich nehme Ihr Anliegen als Nachricht auf und "
                    "leite es weiter. Ein Mitarbeiter meldet sich bei Ihnen."
                ),
                reasoning="Fallback nach Fehler",
            )

    async def summarize(self, session: CallSession) -> CallSummary:
        """Erzeugt die strukturierte Gesprächszusammenfassung."""
        dept_name, *_ = self.directory.routing_target(session.department_id)
        system = (
            "Fasse das folgende Telefongespräch sachlich für den zuständigen "
            "Mitarbeiter zusammen. Nutze ausschließlich das Tool "
            "'zusammenfassung_erstellen'. Antworte auf Deutsch."
        )
        transcript = session.transcript() or "(kein Wortlaut erfasst)"
        try:
            response = await self.client.messages.create(
                model=self.model,
                max_tokens=1024,
                system=system,
                messages=[{"role": "user", "content": f"Gesprächsprotokoll:\n\n{transcript}"}],
                tools=[SUMMARY_TOOL],
                tool_choice={"type": "tool", "name": "zusammenfassung_erstellen"},
            )
            p = _extract_tool_input(response, "zusammenfassung_erstellen")
            return CallSummary(
                caller_number=session.caller_number,
                department_id=session.department_id,
                department_name=dept_name,
                subject=p["subject"],
                summary=p["summary"],
                caller_request=p["caller_request"],
                callback_requested=p.get("callback_requested", False),
                callback_number=p.get("callback_number") or session.caller_number,
                urgency=p.get("urgency", "normal"),
            )
        except Exception:  # pragma: no cover
            logger.exception("Zusammenfassung fehlgeschlagen – nutze Rohprotokoll")
            return CallSummary(
                caller_number=session.caller_number,
                department_id=session.department_id,
                department_name=dept_name,
                subject="Anruf eingegangen",
                summary="Automatische Zusammenfassung nicht verfügbar. Siehe Wortlaut.",
                caller_request=transcript,
                callback_number=session.caller_number,
            )


def _extract_tool_input(response, tool_name: str) -> dict:
    """Holt die strukturierte Eingabe des angeforderten Tools aus der Antwort."""
    for block in response.content:
        if getattr(block, "type", None) == "tool_use" and block.name == tool_name:
            return block.input
    raise ValueError(f"Tool-Antwort '{tool_name}' nicht gefunden: {response}")
