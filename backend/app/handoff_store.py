"""进程内转人工状态记录。

1.0 只做单向通知，但用一个按 WAID 的状态表记录"该会话已经转人工"，用于：
- 去重/冷却：已转人工后，后续连续答不出/报错不再重复通知值班人；
- 双向扩展点：v2 做值班人↔客户中继时，可凭此找到客户会话并把值班人回复转发回去
  （staff_wa_id 字段即为该接缝预留）。

单实例单 worker 下用 dict + 锁即可；升级多副本时替换为 Redis 实现，接口不变。
状态随会话 TTL 过期，或在客户发 reset 时显式清除。
"""
import threading
import time
from dataclasses import dataclass
from typing import Callable

_clock: Callable[[], float] = time.time

# 转人工原因（也用于通知标题映射，见 handoff.py）
HandoffReason = str  # "customer_request" | "auto_no_answer" | "ai_error"


@dataclass
class HandoffState:
    active: bool = False
    reason: HandoffReason = ""
    notified: bool = False        # 是否成功通知到值班人（主号或备用号）
    ts: float = 0.0
    staff_wa_id: str | None = None  # v2 双向中继：接手的值班人号码（v1 不写）


class HandoffStore:
    def __init__(self, ttl_seconds: int) -> None:
        self._ttl = ttl_seconds
        self._states: dict[str, HandoffState] = {}
        self._lock = threading.RLock()

    def mark_active(
        self, wa_id: str, reason: HandoffReason, notified: bool
    ) -> HandoffState:
        """标记该会话已转人工（成功通知后调用）。"""
        with self._lock:
            state = HandoffState(
                active=True,
                reason=reason,
                notified=notified,
                ts=_clock(),
            )
            self._states[wa_id] = state
            return state

    def is_active(self, wa_id: str) -> bool:
        """该会话当前是否处于"已转人工"状态（未过 TTL）。过期顺带清除。"""
        with self._lock:
            return self.get_active(wa_id) is not None

    def get_active(self, wa_id: str) -> HandoffState | None:
        with self._lock:
            state = self._states.get(wa_id)
            if state is None:
                return None
            if _clock() - state.ts > self._ttl:
                del self._states[wa_id]
                return None
            return state

    def clear(self, wa_id: str) -> None:
        """清除转人工状态（客户 reset，或 v2 值班人关闭会话时）。"""
        with self._lock:
            self._states.pop(wa_id, None)
