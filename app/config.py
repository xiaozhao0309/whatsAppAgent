"""集中读取环境变量配置。可理解成"全局配置单"。"""
import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()  # 从 .env 文件加载到环境变量


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True)
class Settings:
    # --- Twilio ---
    twilio_account_sid: str
    twilio_auth_token: str
    twilio_whatsapp_number: str

    # --- 火山方舟 Ark ---
    ark_api_key: str
    ark_base_url: str
    ark_model: str

    # --- Qdrant ---
    qdrant_path: str
    qdrant_collection: str

    # --- RAG ---
    chunk_size: int
    chunk_overlap: int
    top_k: int
    rag_score_threshold: float
    answer_max_chars: int

    # --- 会话（多轮对话）---
    session_ttl_seconds: int
    session_max_turns: int
    session_max_chars: int

    # --- 防滥用 ---
    rate_limit_per_minute: int
    message_max_chars: int

    # --- 转人工 ---
    on_duty_number: str
    on_duty_fallback_number: str


settings = Settings(
    twilio_account_sid=os.getenv("TWILIO_ACCOUNT_SID", ""),
    twilio_auth_token=os.getenv("TWILIO_AUTH_TOKEN", ""),
    twilio_whatsapp_number=os.getenv("TWILIO_WHATSAPP_NUMBER", "whatsapp:+14155238886"),
    ark_api_key=os.getenv("ARK_API_KEY", ""),
    ark_base_url=os.getenv(
        "ARK_BASE_URL",
        "https://ark.cn-beijing.volces.com/api/v3",
    ),
    ark_model=os.getenv("ARK_MODEL", ""),
    qdrant_path=os.getenv("QDRANT_PATH", "./data/qdrant"),
    qdrant_collection=os.getenv("QDRANT_COLLECTION", "enterprise_kb"),
    chunk_size=_int("CHUNK_SIZE", 800),
    chunk_overlap=_int("CHUNK_OVERLAP", 100),
    top_k=_int("TOP_K", 5),
    rag_score_threshold=float(os.getenv("RAG_SCORE_THRESHOLD", "0.5")),
    answer_max_chars=_int("ANSWER_MAX_CHARS", 800),
    session_ttl_seconds=_int("SESSION_TTL_SECONDS", 7 * 24 * 3600),
    session_max_turns=_int("SESSION_MAX_TURNS", 10),
    session_max_chars=_int("SESSION_MAX_CHARS", 2000),
    rate_limit_per_minute=_int("RATE_LIMIT_PER_MINUTE", 10),
    message_max_chars=_int("MESSAGE_MAX_CHARS", 2000),
    on_duty_number=os.getenv("ON_DUTY_NUMBER", ""),
    on_duty_fallback_number=os.getenv("ON_DUTY_FALLBACK_NUMBER", ""),
)
