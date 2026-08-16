"""Backend configuration: all settings come from environment variables."""
import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()  # loads .env from the directory the process is run from


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True)
class Settings:
    # --- Twilio ---
    twilio_account_sid: str
    twilio_auth_token: str
    twilio_whatsapp_number: str

    # --- AI/RAG service (HTTP) ---
    rag_service_url: str
    rag_timeout: float

    # --- Sessions (multi-turn) ---
    session_ttl_seconds: int
    session_max_turns: int
    session_max_chars: int

    # --- Anti-abuse ---
    rate_limit_per_minute: int
    message_max_chars: int

    # --- Hand-off to human ---
    on_duty_number: str
    on_duty_fallback_number: str


settings = Settings(
    twilio_account_sid=os.getenv("TWILIO_ACCOUNT_SID", ""),
    twilio_auth_token=os.getenv("TWILIO_AUTH_TOKEN", ""),
    twilio_whatsapp_number=os.getenv("TWILIO_WHATSAPP_NUMBER", "whatsapp:+14155238886"),
    rag_service_url=os.getenv("RAG_SERVICE_URL", "http://localhost:8001"),
    rag_timeout=_float("RAG_TIMEOUT", 30.0),
    session_ttl_seconds=_int("SESSION_TTL_SECONDS", 7 * 24 * 3600),
    session_max_turns=_int("SESSION_MAX_TURNS", 10),
    session_max_chars=_int("SESSION_MAX_CHARS", 2000),
    rate_limit_per_minute=_int("RATE_LIMIT_PER_MINUTE", 10),
    message_max_chars=_int("MESSAGE_MAX_CHARS", 2000),
    on_duty_number=os.getenv("ON_DUTY_NUMBER", ""),
    on_duty_fallback_number=os.getenv("ON_DUTY_FALLBACK_NUMBER", ""),
)
