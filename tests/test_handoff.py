"""转人工测试：mock 通道发送，验证上下文组装、主备回退、未配置降级。"""
from types import SimpleNamespace

import app.handoff as handoff
from app.session import SessionStore


def _fake_settings(primary, fallback):
    return SimpleNamespace(
        on_duty_number=primary, on_duty_fallback_number=fallback
    )


def _store_with_history():
    store = SessionStore(ttl_seconds=100, max_turns=10, max_chars=4000)
    store.add_turn("u", "user", "年假几天")
    store.add_turn("u", "assistant", "5 天")
    store.add_turn("u", "user", "那病假呢")
    return store


def test_handoff_sends_to_primary(monkeypatch):
    sent = []

    def fake_send(to, body):
        sent.append((to, body))

    monkeypatch.setattr(handoff, "send_whatsapp", fake_send)
    monkeypatch.setattr(
        handoff, "settings", _fake_settings("whatsapp:+111", "whatsapp:+222")
    )

    store = _store_with_history()
    ok = handoff.trigger_handoff(store, "u", "那病假呢", reason="customer_request")
    assert ok is True
    assert len(sent) == 1
    to, body = sent[0]
    assert to == "whatsapp:+111"
    assert "年假几天" in body and "那病假呢" in body


def test_handoff_falls_back_to_secondary(monkeypatch):
    calls = []

    def fake_send(to, body):
        calls.append(to)
        if to == "whatsapp:+111":
            raise RuntimeError("primary down")

    monkeypatch.setattr(handoff, "send_whatsapp", fake_send)
    monkeypatch.setattr(
        handoff, "settings", _fake_settings("whatsapp:+111", "whatsapp:+222")
    )

    store = _store_with_history()
    ok = handoff.trigger_handoff(store, "u", "q")
    assert ok is True
    assert calls == ["whatsapp:+111", "whatsapp:+222"]


def test_handoff_unconfigured_returns_false(monkeypatch):
    monkeypatch.setattr(handoff, "send_whatsapp", lambda to, body: None)
    monkeypatch.setattr(handoff, "settings", _fake_settings("", ""))
    store = _store_with_history()
    ok = handoff.trigger_handoff(store, "u", "q")
    assert ok is False
