"""转人工：把客户问题与最近对话上下文通知值班人员。

1.0 为单向通知（方案 A）：机器人把上下文发给值班号码，不做值班人↔客户的双向中继。
"""
import logging

from .channel import send_whatsapp
from .config import settings
from .session import SessionStore

log = logging.getLogger("whatsapp_agent")

HANDOFF_CONTEXT_TURNS = 5
HANDOFF_CONTEXT_CHARS = 2000


def _build_context(store: SessionStore, wa_id: str, question: str) -> str:
    """组装发送给值班人的通知正文。"""
    turns, _ = store.build_context(wa_id)
    recent = turns[-HANDOFF_CONTEXT_TURNS:] if turns else []
    lines = []
    for t in recent:
        speaker = "客户" if t.role == "user" else "助手"
        lines.append(f"{speaker}: {t.content[:300]}")
    context_text = "\n".join(lines)
    if len(context_text) > HANDOFF_CONTEXT_CHARS:
        context_text = context_text[-HANDOFF_CONTEXT_CHARS:]

    last_q = question or store.last_user_question(wa_id) or "(无明确问题)"
    return (
        "🔔 转人工请求\n"
        f"客户：{wa_id}\n"
        f"问题：{last_q}\n"
        "--- 最近对话 ---\n"
        f"{context_text or '(无)'}"
    )


def trigger_handoff(
    store: SessionStore,
    wa_id: str,
    question: str,
    reason: str = "customer_request",
) -> bool:
    """向值班号码发送转人工通知。

    返回 True 表示成功通知到（主号或备用号）；False 表示无法通知（未配置/发送失败）。
    不抛异常，调用方据此决定给客户的回复。
    """
    body = _build_context(store, wa_id, question)
    if reason == "auto_no_answer":
        body = "🔔 连续未答出，自动转人工\n" + body.split("\n", 1)[1]

    primary = settings.on_duty_number
    fallback = settings.on_duty_fallback_number

    for target in [primary, fallback]:
        if not target:
            continue
        try:
            send_whatsapp(target, body)
            log.info("转人工通知已发送 reason=%s target=%s", reason, target)
            return True
        except Exception:
            log.exception("转人工通知发送失败 target=%s", target)
    if not primary:
        log.warning("未配置值班号码 ON_DUTY_NUMBER，转人工降级")
    return False
