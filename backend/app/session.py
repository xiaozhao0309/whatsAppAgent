"""进程内会话管理。

以 WhatsApp 号码（WAID）为键保存最近对话轮次，支持：
- 7 天滑动过期（每次有效交互刷新）
- 最多保留 N 轮
- 组装上下文时按字符上限从最早轮截断
- 连续拒答计数（用于自动转人工）
- "最后一条助手消息是否已评价"标记（反馈去重）

单实例单 worker 下用 dict + 锁即可；升级多副本时替换为 Redis 实现，接口不变。
"""
import threading
import time
from dataclasses import dataclass, field
from typing import Callable

_clock: Callable[[], float] = time.time


@dataclass
class Turn:
    role: str  # "user" | "assistant"
    content: str
    ts: float


@dataclass
class SessionState:
    turns: list[Turn] = field(default_factory=list)
    last_active_ts: float = 0.0
    miss_streak: int = 0
    last_answer_feedback: str | None = None  # None=未评价, "up"/"down"=已评价


class SessionStore:
    def __init__(self, ttl_seconds: int, max_turns: int, max_chars: int) -> None:
        self._ttl = ttl_seconds
        self._max_turns = max_turns
        self._max_chars = max_chars
        self._sessions: dict[str, SessionState] = {}
        self._lock = threading.RLock()

    def _get_or_create(self, wa_id: str) -> SessionState:
        return self._sessions.setdefault(wa_id, SessionState(last_active_ts=_clock()))

    def is_expired(self, wa_id: str) -> bool:
        """会话是否已过期（或不存在）。过期会顺带清除旧会话。"""
        with self._lock:
            state = self._sessions.get(wa_id)
            if state is None:
                return True
            if _clock() - state.last_active_ts > self._ttl:
                del self._sessions[wa_id]
                return True
            return False

    def exists(self, wa_id: str) -> bool:
        with self._lock:
            state = self._sessions.get(wa_id)
            return state is not None and not self.is_expired(wa_id)

    def state(self, wa_id: str) -> str:
        """返回会话状态：'absent'（从未有过）/ 'expired'（曾有但过期，已清除）/ 'active'。"""
        with self._lock:
            s = self._sessions.get(wa_id)
            if s is None:
                return "absent"
            if _clock() - s.last_active_ts > self._ttl:
                del self._sessions[wa_id]
                return "expired"
            return "active"

    def reset(self, wa_id: str) -> None:
        with self._lock:
            self._sessions.pop(wa_id, None)

    def get_history(self, wa_id: str) -> list[Turn]:
        """返回当前会话的历史轮次（已做轮数与字符截断）。过期则返回空。"""
        with self._lock:
            state = self._sessions.get(wa_id)
            if state is None or _clock() - state.last_active_ts > self._ttl:
                return []
            return list(state.turns)

    def add_turn(self, wa_id: str, role: str, content: str) -> None:
        """追加一轮，并应用轮数截断与 TTL 刷新。"""
        with self._lock:
            state = self._get_or_create(wa_id)
            state.turns.append(Turn(role=role, content=content, ts=_clock()))
            # 轮数截断：保留最近 max_turns 轮
            if len(state.turns) > self._max_turns:
                state.turns = state.turns[-self._max_turns:]
            # 新回答重置反馈标记，使新回答可被评价
            if role == "assistant":
                state.last_answer_feedback = None
            state.last_active_ts = _clock()

    def build_context(self, wa_id: str) -> tuple[list[Turn], str]:
        """组装用于 LLM 的历史，按字符上限从最早轮截断。

        返回 (使用的轮次列表, 拼接后的上下文字符串)。
        """
        turns = self.get_history(wa_id)
        kept: list[Turn] = []
        total = 0
        # 从最近一轮向前累加，超限即停
        for turn in reversed(turns):
            length = len(turn.content)
            if total + length > self._max_chars and kept:
                break
            kept.append(turn)
            total += length
        kept.reverse()
        context = "\n".join(f"{t.role}: {t.content}" for t in kept)
        return kept, context

    # --- 连续拒答计数 ---
    def record_miss(self, wa_id: str) -> int:
        with self._lock:
            state = self._get_or_create(wa_id)
            state.miss_streak += 1
            state.last_active_ts = _clock()
            return state.miss_streak

    def record_hit(self, wa_id: str) -> None:
        with self._lock:
            state = self._sessions.get(wa_id)
            if state is not None:
                state.miss_streak = 0

    def get_miss_streak(self, wa_id: str) -> int:
        with self._lock:
            state = self._sessions.get(wa_id)
            return state.miss_streak if state else 0

    # --- 反馈去重 ---
    def try_mark_feedback(self, wa_id: str, value: str) -> bool:
        """把最后一条助手回答标记为已评价。

        返回 True 表示本次反馈有效；False 表示此前已评价过（去重）。
        """
        with self._lock:
            state = self._sessions.get(wa_id)
            if state is None or not state.turns:
                return False  # 没有可评价的回答
            if state.last_answer_feedback is not None:
                return False
            state.last_answer_feedback = value
            return True

    def last_user_question(self, wa_id: str) -> str:
        """取最后一条 user 消息（转人工通知用）。"""
        with self._lock:
            state = self._sessions.get(wa_id)
            if not state or not state.turns:
                return ""
            for turn in reversed(state.turns):
                if turn.role == "user":
                    return turn.content
            return ""
