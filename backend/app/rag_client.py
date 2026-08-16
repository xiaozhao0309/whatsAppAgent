"""HTTP client for the AI/RAG service.

The backend never imports RAG code directly. It calls the AI service over HTTP
using this client. The request/response shape here is the contract between the
backend person and the AI person: keep it in sync with ai_service/app/main.py.
"""
from dataclasses import dataclass, field
from typing import Literal

import requests

AnswerStatus = Literal["answered", "no_match", "empty_kb", "error"]


class RAGServiceError(RuntimeError):
    """Raised when the AI service is unreachable or returns an error."""


@dataclass
class AnswerResult:
    reply: str
    sources: list[str] = field(default_factory=list)
    status: AnswerStatus = "answered"
    top_score: float | None = None


class RAGClient:
    def __init__(self, base_url: str, timeout: float = 30.0):
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    def answer(self, question: str, history: list[dict] | None = None) -> AnswerResult:
        payload = {"question": question, "history": history or []}
        data = self._post("/answer", payload)
        return AnswerResult(
            reply=data.get("reply", ""),
            sources=list(data.get("sources", [])),
            status=data.get("status", "error"),
            top_score=data.get("top_score"),
        )

    def ingest(self) -> int:
        data = self._post("/ingest", {})
        return int(data.get("ingested_chunks", 0))

    def health(self) -> dict:
        try:
            resp = requests.get(
                f"{self._base_url}/health", timeout=min(self._timeout, 5.0)
            )
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as e:
            raise RAGServiceError(f"AI service health check failed: {e}") from e

    def _post(self, path: str, payload: dict) -> dict:
        try:
            resp = requests.post(
                f"{self._base_url}{path}", json=payload, timeout=self._timeout
            )
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as e:
            raise RAGServiceError(f"AI service call to {path} failed: {e}") from e
