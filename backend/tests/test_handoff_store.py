"""转人工状态存储测试。"""
import time

import app.handoff_store as hs_mod
from app.handoff_store import HandoffStore


def _set_time(t: float) -> None:
    hs_mod._clock = lambda: t


def test_mark_active_and_is_active():
    store = HandoffStore(ttl_seconds=100)
    _set_time(1000.0)
    assert store.is_active("u") is False
    state = store.mark_active("u", reason="auto_no_answer", notified=True)
    assert state.reason == "auto_no_answer" and state.notified is True
    assert store.is_active("u") is True
    assert store.get_active("u").reason == "auto_no_answer"


def test_clear():
    store = HandoffStore(ttl_seconds=100)
    _set_time(1000.0)
    store.mark_active("u", reason="customer_request", notified=True)
    store.clear("u")
    assert store.is_active("u") is False


def test_ttl_expiry():
    store = HandoffStore(ttl_seconds=10)
    _set_time(1000.0)
    store.mark_active("u", reason="ai_error", notified=True)
    _set_time(1011.0)
    assert store.is_active("u") is False
    assert store.get_active("u") is None
