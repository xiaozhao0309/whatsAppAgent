"""幂等、限流、长度校验测试。"""
import app.guards as guards


def test_idempotency_blocks_duplicate():
    g = guards.IdempotencyGuard(ttl_seconds=100)
    assert g.seen_or_mark("msg-1") is False  # 首次
    assert g.seen_or_mark("msg-1") is True   # 重复
    assert g.seen_or_mark("msg-2") is False  # 另一条


def test_idempotency_ttl_expiry():
    g = guards.IdempotencyGuard(ttl_seconds=10)
    t = [1000.0]
    guards._clock = lambda: t[0]

    assert g.seen_or_mark("msg-1") is False
    t[0] += 5
    assert g.seen_or_mark("msg-1") is True   # 未过期
    t[0] += 6
    assert g.seen_or_mark("msg-1") is False  # 已过期，重新标记


def test_ratelimiter_blocks_over_limit():
    rl = guards.RateLimiter(max_per_minute=2, window_seconds=60)
    t = [1000.0]
    guards._clock = lambda: t[0]

    assert rl.allow("user-1") is True
    assert rl.allow("user-1") is True
    assert rl.allow("user-1") is False  # 第 3 次被限流
    assert rl.allow("user-2") is True   # 不同用户独立计数


def test_ratelimiter_window_rolls_over():
    rl = guards.RateLimiter(max_per_minute=2, window_seconds=60)
    t = [1000.0]
    guards._clock = lambda: t[0]

    assert rl.allow("user-1") is True
    assert rl.allow("user-1") is True
    t[0] += 61  # 翻过窗口
    assert rl.allow("user-1") is True


def test_message_length():
    assert guards.check_message_length("短消息", 10) is True
    assert guards.check_message_length("a" * 11, 10) is False
    assert guards.check_message_length("", 10) is True
