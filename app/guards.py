"""入站防护：幂等去重、限流、消息长度校验。

1.0 单实例部署，状态全部放在进程内存（dict + 锁），惰性清理过期条目。
升级多副本时，把这些实现替换为 Redis 即可，接口保持不变。
"""
import threading
import time
from typing import Callable

# 注入时间源，便于测试（避免测试中真实 sleep）
_clock: Callable[[], float] = time.time

IDEMPOTENCY_TTL_SECONDS = 24 * 3600  # MessageSid 去重窗口（覆盖 Twilio 重试）
RATE_LIMIT_WINDOW_SECONDS = 60


class IdempotencyGuard:
    """基于消息唯一标识去重，防止通道重试导致重复回复（FR-027）。"""

    def __init__(self, ttl_seconds: int = IDEMPOTENCY_TTL_SECONDS) -> None:
        self._ttl = ttl_seconds
        self._seen: dict[str, float] = {}
        self._lock = threading.Lock()

    def seen_or_mark(self, message_id: str) -> bool:
        """返回 True 表示此前已见过（应丢弃）；False 表示首次见到并已标记。"""
        if not message_id:
            return False
        now = _clock()
        with self._lock:
            self._purge(now)
            exp = self._seen.get(message_id)
            if exp is not None and exp > now:
                return True
            self._seen[message_id] = now + self._ttl
            return False

    def _purge(self, now: float) -> None:
        expired = [k for k, v in self._seen.items() if v <= now]
        for k in expired:
            del self._seen[k]

    def reset(self) -> None:
        with self._lock:
            self._seen.clear()


class RateLimiter:
    """按身份标识的固定时间窗限流器（FR-025）。"""

    def __init__(self, max_per_minute: int, window_seconds: int = RATE_LIMIT_WINDOW_SECONDS) -> None:
        self._max = max_per_minute
        self._window = window_seconds
        self._buckets: dict[str, tuple[float, int]] = {}
        self._lock = threading.Lock()

    def allow(self, identity: str) -> bool:
        """检查该身份是否还能继续请求；超过阈值返回 False。"""
        if not identity or self._max <= 0:
            return True
        now = _clock()
        with self._lock:
            window_start, count = self._buckets.get(identity, (now, 0))
            if now - window_start >= self._window:
                # 翻窗
                window_start, count = now, 0
            if count >= self._max:
                self._buckets[identity] = (window_start, count)
                return False
            count += 1
            self._buckets[identity] = (window_start, count)
            return True

    def reset(self) -> None:
        with self._lock:
            self._buckets.clear()


def check_message_length(body: str, max_chars: int) -> bool:
    """消息长度是否在允许范围内（FR-026）。超长返回 False。"""
    return len(body or "") <= max_chars
