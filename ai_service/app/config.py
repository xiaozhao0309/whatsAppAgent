"""AI service configuration: all settings come from environment variables."""
import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()  # loads .env from the directory the process is run from


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True)
class Settings:
    # --- Volcano Ark (LLM) ---
    ark_api_key: str
    ark_base_url: str
    ark_model: str

    # --- Qdrant (local-file vector store) ---
    qdrant_path: str
    qdrant_collection: str

    # --- RAG tuning ---
    chunk_size: int
    chunk_overlap: int
    top_k: int
    rag_score_threshold: float
    answer_max_chars: int

    # --- Knowledge base source documents ---
    docs_dir: str


settings = Settings(
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
    docs_dir=os.getenv("DOCS_DIR", "./app/sample_docs"),
)
