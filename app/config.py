"""集中读取环境变量配置。可理解成"全局配置单"。"""
import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()  # 从 .env 文件加载到环境变量


@dataclass(frozen=True)
class Settings:
    # --- Twilio ---
    twilio_account_sid: str
    twilio_auth_token: str
    twilio_whatsapp_number: str

    # # --- Anthropic ---
    # anthropic_api_key: str
    # anthropic_base_url: str
    # anthropic_model: str
    
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


settings = Settings(
    twilio_account_sid=os.getenv("TWILIO_ACCOUNT_SID", ""),
    twilio_auth_token=os.getenv("TWILIO_AUTH_TOKEN", ""),
    twilio_whatsapp_number=os.getenv("TWILIO_WHATSAPP_NUMBER", "whatsapp:+14155238886"),
    # anthropic_api_key=os.getenv("ANTHROPIC_API_KEY", ""),
    # anthropic_base_url=os.getenv("ANTHROPIC_BASE_URL", ""),
    # anthropic_model=os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5"),
    ark_api_key=os.getenv("ARK_API_KEY", ""),
    ark_base_url=os.getenv(
        "ARK_BASE_URL",
        "https://ark.cn-beijing.volces.com/api/v3",
    ),
    ark_model=os.getenv("ARK_MODEL", ""),
    qdrant_path=os.getenv("QDRANT_PATH", "./data/qdrant"),
    qdrant_collection=os.getenv("QDRANT_COLLECTION", "enterprise_kb"),
    chunk_size=int(os.getenv("CHUNK_SIZE", "800")),
    chunk_overlap=int(os.getenv("CHUNK_OVERLAP", "100")),
    top_k=int(os.getenv("TOP_K", "5")),
)
