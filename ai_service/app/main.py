"""AI/RAG service: exposes retrieval + generation over HTTP.

Endpoints:
- POST /answer  -> {question, history} -> {reply, sources, status, top_score}
- POST /ingest  -> rebuild the knowledge base from sample_docs/
- GET  /health  -> KB status (points, accessibility)

This service owns the embedding model, Qdrant store, and LLM client.
The backend WhatsApp service calls /answer and stays independent of all of it.
"""
import logging
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI
from pydantic import BaseModel

from .config import settings
from .rag.embeddings import embed_one
from .rag.ingest import ingest_directory
from .rag.pipeline import answer
from .rag.store import count_points, ensure_collection

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("ai_service")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Ensure the collection exists and preload the embedding model so the
    # first /answer request isn't slow.
    ensure_collection()
    try:
        log.info("warming up embedding model ...")
        embed_one("warmup")
        log.info("embedding model ready")
    except Exception:
        log.exception("embedding model warmup failed (will retry on first request)")
    yield


app = FastAPI(title="WhatsApp Agent - AI/RAG Service", lifespan=lifespan)


class Turn(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class AnswerRequest(BaseModel):
    question: str
    history: list[Turn] = []


class AnswerResponse(BaseModel):
    reply: str
    sources: list[str] = []
    status: Literal["answered", "no_match", "empty_kb", "error"]
    top_score: float | None = None


@app.get("/health")
def health():
    try:
        points = count_points()
        return {
            "status": "ok",
            "kb": {
                "collection": settings.qdrant_collection,
                "points": points,
                "accessible": True,
            },
        }
    except Exception as e:
        log.exception("health check failed")
        return {
            "status": "degraded",
            "kb": {
                "collection": settings.qdrant_collection,
                "accessible": False,
                "error": str(e),
            },
        }


@app.post("/answer", response_model=AnswerResponse)
def answer_endpoint(req: AnswerRequest):
    history = [t.model_dump() for t in req.history]
    result = answer(req.question, history=history)
    return AnswerResponse(
        reply=result.reply,
        sources=result.sources,
        status=result.status,  # type: ignore[arg-type]
        top_score=result.top_score,
    )


@app.post("/ingest")
def ingest():
    """Full rebuild of the knowledge base from the configured docs directory."""
    total = ingest_directory(settings.docs_dir, rebuild=True)
    return {"ingested_chunks": total}
