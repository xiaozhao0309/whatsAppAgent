"""Tests for the HTTP client that talks to the AI/RAG service."""
from types import SimpleNamespace

import pytest

from app.rag_client import RAGClient, RAGServiceError


class _FakeResp:
    def __init__(self, json_data=None, status=200, raise_exc=None):
        self._json = json_data or {}
        self.status_code = status
        self._raise_exc = raise_exc

    def json(self):
        return self._json

    def raise_for_status(self):
        if self._raise_exc:
            raise self._raise_exc


def test_answer_contract(monkeypatch):
    captured = {}

    def fake_post(url, json, timeout):
        captured["url"] = url
        captured["json"] = json
        captured["timeout"] = timeout
        return _FakeResp({
            "reply": "5 days [Source: hr.md]",
            "sources": ["hr.md"],
            "status": "answered",
            "top_score": 0.83,
        })

    monkeypatch.setattr("app.rag_client.requests.post", fake_post)
    client = RAGClient("http://localhost:8001/", timeout=10)

    result = client.answer("How many leave days?", history=[{"role": "user", "content": "hi"}])

    assert result.reply == "5 days [Source: hr.md]"
    assert result.sources == ["hr.md"]
    assert result.status == "answered"
    assert result.top_score == 0.83
    assert captured["url"] == "http://localhost:8001/answer"
    assert captured["json"] == {
        "question": "How many leave days?",
        "history": [{"role": "user", "content": "hi"}],
    }


def test_ingest(monkeypatch):
    monkeypatch.setattr(
        "app.rag_client.requests.post",
        lambda url, json, timeout: _FakeResp({"ingested_chunks": 33}),
    )
    client = RAGClient("http://localhost:8001")
    assert client.ingest() == 33


def test_connection_error_raises(monkeypatch):
    import requests

    def fake_post(url, json, timeout):
        raise requests.ConnectionError("refused")

    monkeypatch.setattr("app.rag_client.requests.post", fake_post)
    client = RAGClient("http://localhost:8001")
    with pytest.raises(RAGServiceError):
        client.answer("anything")


def test_health_failure_raises(monkeypatch):
    import requests

    monkeypatch.setattr(
        "app.rag_client.requests.get",
        lambda url, timeout: (_ for _ in ()).throw(requests.Timeout("slow")),
    )
    client = RAGClient("http://localhost:8001")
    with pytest.raises(RAGServiceError):
        client.health()
