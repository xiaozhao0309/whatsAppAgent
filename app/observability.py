"""可观测性辅助：请求 ID、号码脱敏、结构化日志。

宪法原则 IV：记录关键路径日志，但不记录密钥、完整号码或完整隐私内容；
异常通过 logger.exception 保留堆栈。
"""
import logging
import re
import time
import uuid
from contextlib import contextmanager

log = logging.getLogger("whatsapp_agent")


def new_request_id() -> str:
    """生成短请求 ID，用于串联一条消息的所有日志。"""
    return uuid.uuid4().hex[:12]


def mask_waid(waid: str) -> str:
    """脱敏 WhatsApp 号码。

    形如 whatsapp:+8613812345678 -> whatsapp:+86****5678
    保留前缀、国家码前两位与末 4 位，足以排查又不泄露完整号码。
    """
    if not waid:
        return ""
    m = re.match(r"^(whatsapp:)?(\+?\d+)$", waid)
    if not m:
        # 非预期格式，整体打码
        return "****"
    prefix, num = m.group(1) or "", m.group(2)
    if len(num) <= 6:
        masked = "*" * len(num)
    else:
        masked = num[:2] + "*" * (len(num) - 6) + num[-4:]
    return f"{prefix}{masked}"


def log_event(request_id: str, event: str, **fields) -> None:
    """结构化日志：固定字段在前，附加字段在后。

    调用方负责不要把密钥/完整号码/完整对话正文传进来；
    号码请用 mask_waid 脱敏。
    """
    entry = {"request_id": request_id, "event": event}
    entry.update(fields)
    log.info("event=%s %s", event, _format_kv(entry))


def _format_kv(d: dict) -> str:
    parts = []
    for k, v in d.items():
        if k in ("event",):
            continue
        parts.append(f"{k}={v!r}")
    return " ".join(parts)


@contextmanager
def timed(request_id: str, operation: str):
    """记录某段操作的耗时（毫秒）。"""
    start = time.perf_counter()
    try:
        yield
    finally:
        elapsed_ms = (time.perf_counter() - start) * 1000
        log_event(request_id, f"{operation}_done", elapsed_ms=round(elapsed_ms))
