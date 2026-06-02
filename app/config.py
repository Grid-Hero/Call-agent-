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

    # Gesprächsmodus
    # "gather"   -> Turn-by-turn (Twilio <Gather>/<Say>), einfach & robust
    # "realtime" -> Echtzeit-Audio via Twilio Media Streams (ElevenLabs, optional Deepgram)
    conversation_mode: str = "gather"

    # Telefonie
    telephony_provider: str = "twilio"
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_phone_number: str = ""
    twilio_validate_signature: bool = True

    # Anthropic / Claude
    anthropic_api_key: str = ""
    # Für Telefon-Agenten ist Haiku ideal: schnell, selten überlastet, günstig.
    anthropic_model: str = "claude-haiku-4-5-20251001"
    # Ausweichmodell, falls das Hauptmodell überlastet ist (529).
    anthropic_fallback_model: str = "claude-sonnet-4-6"
    agent_language: str = "de-DE"
    agent_company_name: str = "Musterfirma GmbH"

    # Text-to-Speech (Stimme des Agents)
    # "twilio"     -> eingebaute Twilio-Stimme (<Say>)
    # "elevenlabs" -> ElevenLabs-Stimme (<Play> mit synthetisiertem Audio)
    tts_provider: str = "twilio"
    # Stimme für TTS_PROVIDER=twilio. Neuronale Amazon-Polly-Stimme klingt
    # deutlich natürlicher als die Basis-Stimme (z.B. Polly.Vicki-Neural,
    # Polly.Daniel-Neural). Kostet bei Twilio nichts extra.
    twilio_voice: str = "Polly.Vicki-Neural"
    elevenlabs_api_key: str = ""
    elevenlabs_voice_id: str = ""
    # Mehrsprachiges Modell (unterstützt Deutsch). Alternativen: eleven_turbo_v2_5 (geringere Latenz)
    elevenlabs_model: str = "eleven_multilingual_v2"
    elevenlabs_output_format: str = "mp3_44100_128"

    # Speech-to-Text (nur im Echtzeit-Modus)
    # "elevenlabs" -> ein Account für STT + TTS (kein Extra-Dienst nötig)
    # "deepgram"   -> Alternative
    stt_provider: str = "elevenlabs"
    # ElevenLabs Scribe (Realtime-STT). Werte ggf. an die ElevenLabs-Doku anpassen.
    elevenlabs_stt_model: str = "scribe_v2_realtime"
    elevenlabs_stt_encoding: str = "ulaw"  # Twilio μ-law; Sample-Rate 8000
    # Deepgram (optional, nur falls STT_PROVIDER=deepgram)
    deepgram_api_key: str = ""
    deepgram_model: str = "nova-2"
    deepgram_language: str = "de"

    @property
    def stt_language(self) -> str:
        """STT-Sprachcode aus AGENT_LANGUAGE (z.B. 'de-DE' -> 'de')."""
        return self.agent_language.split("-")[0]

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

    # Persistente Speicherung der Konfiguration in GitHub (optional).
    # Wenn Token + Repo gesetzt sind, schreibt /admin Änderungen als Commit
    # ins Repo und lädt beim Start von dort (überlebt Render-Neustarts).
    github_token: str = ""
    github_repo: str = ""          # Format: "owner/repo", z.B. "Grid-Hero/Call-agent-"
    github_branch: str = "main"
    github_config_path: str = "config/directory.yaml"

    # Admin-Weboberfläche (/admin). Ohne gesetztes Passwort ist sie deaktiviert.
    admin_password: str = ""
    admin_user: str = "admin"

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() == "production"

    @property
    def effective_base_url(self) -> str:
        """Öffentliche Basis-URL der App.

        Bevorzugt APP_BASE_URL; fällt sonst auf RENDER_EXTERNAL_URL zurück, das
        Render-Hosting automatisch bereitstellt. So muss die URL nach dem ersten
        Deploy nicht manuell nachgetragen werden.
        """
        import os

        if self.app_base_url and "localhost" not in self.app_base_url:
            return self.app_base_url.rstrip("/")
        render_url = os.environ.get("RENDER_EXTERNAL_URL", "")
        return (render_url or self.app_base_url).rstrip("/")

    @property
    def websocket_base_url(self) -> str:
        """Leitet die WebSocket-Basis-URL aus der Basis-URL ab (http->ws, https->wss)."""
        base = self.effective_base_url
        if base.startswith("https://"):
            return "wss://" + base[len("https://") :]
        if base.startswith("http://"):
            return "ws://" + base[len("http://") :]
        return base


@lru_cache
def get_settings() -> Settings:
    """Gibt die (gecachte) Einstellungs-Instanz zurück."""
    return Settings()
