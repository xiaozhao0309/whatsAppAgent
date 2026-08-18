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
    contact_phone_number: str         # 客户转人工时回复的联系电话
    handoff_miss_threshold: int       # 连续答不出多少次后提示联系电话
    handoff_error_threshold: int      # AI 服务连续报错多少次后提示联系电话
    low_confidence_score: float       # answered 且低于此分追加转人工提示；0 关闭


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
    contact_phone_number=os.getenv("CONTACT_PHONE_NUMBER", "020 1234567"),
    handoff_miss_threshold=_int("HANDOFF_MISS_THRESHOLD", 2),
    handoff_error_threshold=_int("HANDOFF_ERROR_THRESHOLD", 2),
    low_confidence_score=_float("LOW_CONFIDENCE_SCORE", 0.6),
)
