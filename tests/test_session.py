"""会话管理测试。"""
import app.session as session_mod
from app.session import SessionStore


def _set_time(t: float) -> None:
    session_mod._clock = lambda: t


def test_turn_truncation():
    store = SessionStore(ttl_seconds=100, max_turns=3, max_chars=10000)
    t = 1000.0
    _set_time(t)
    for i in range(5):
        store.add_turn("u", "user", f"q{i}")
        store.add_turn("u", "assistant", f"a{i}")
        t += 1
        _set_time(t)
    history = store.get_history("u")
    # 最多保留 3 轮（每轮一问一答 -> 这里实际按 turn 计数，保留最近 3 条 turn）
    assert len(history) == 3
    assert history[0].content == "a3"  # 最近的 3 条


def test_char_truncation():
    store = SessionStore(ttl_seconds=100, max_turns=100, max_chars=5)
    _set_time(1000.0)
    store.add_turn("u", "user", "aaaa")      # 4
    store.add_turn("u", "assistant", "bbbb") # 4 -> 累计 8 > 5
    turns, context = store.build_context("u")
    # 从最近向前累加，最近一条 assistant(4) 单独保留
    assert len(turns) == 1
    assert turns[0].content == "bbbb"


def test_sliding_ttl_expiry():
    store = SessionStore(ttl_seconds=10, max_turns=10, max_chars=10000)
    t = 1000.0
    _set_time(t)
    store.add_turn("u", "user", "q")
    assert store.exists("u") is True

    t += 5
    _set_time(t)
    store.add_turn("u", "assistant", "a")  # 活跃刷新
    assert store.exists("u") is True

    t += 11
    _set_time(t)
    assert store.is_expired("u") is True
    assert store.get_history("u") == []


def test_reset_clears_session():
    store = SessionStore(ttl_seconds=100, max_turns=10, max_chars=10000)
    _set_time(1000.0)
    store.add_turn("u", "user", "q")
    store.reset("u")
    assert store.exists("u") is False


def test_miss_streak():
    store = SessionStore(ttl_seconds=100, max_turns=10, max_chars=10000)
    _set_time(1000.0)
    assert store.record_miss("u") == 1
    assert store.record_miss("u") == 2
    store.record_hit("u")
    assert store.get_miss_streak("u") == 0


def test_feedback_dedup():
    store = SessionStore(ttl_seconds=100, max_turns=10, max_chars=10000)
    _set_time(1000.0)
    store.add_turn("u", "user", "q")
    store.add_turn("u", "assistant", "a")
    assert store.try_mark_feedback("u", "up") is True
    assert store.try_mark_feedback("u", "down") is False  # 同轮已评价
    # 新回答后可再次评价
    store.add_turn("u", "user", "q2")
    store.add_turn("u", "assistant", "a2")
    assert store.try_mark_feedback("u", "down") is True
