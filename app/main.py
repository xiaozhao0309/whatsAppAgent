"""FastAPI 入口：接收 Twilio 的 WhatsApp webhook，触发 RAG 问答。

流程：Twilio 把用户消息 POST 到 /webhook -> 立刻回 200（避免超时重试）
-> 在后台跑 RAG -> 用 Twilio REST API 把答案发回用户。

单实例单 worker 运行：会话/幂等/限流均在进程内存。
"""
import logging
import threading
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, Request
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from . import responses
from .channel import send_whatsapp
from .commands import parse_command
from .config import settings
from .guards import IdempotencyGuard, RateLimiter, check_message_length
from .handoff import trigger_handoff
from .observability import log_event, mask_waid, new_request_id
from .rag.embeddings import embed_one
from .rag.ingest import ingest_directory
from .rag.pipeline import answer
from .rag.store import count_points, ensure_collection
from .session import SessionStore

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("whatsapp_agent")

SAMPLE_DOCS_DIR = Path(__file__).resolve().parent / "sample_docs"

# 进程内共享组件（单 worker）
session_store = SessionStore(
    ttl_seconds=settings.session_ttl_seconds,
    max_turns=settings.session_max_turns,
    max_chars=settings.session_max_chars,
)
idempotency = IdempotencyGuard()
rate_limiter = RateLimiter(max_per_minute=settings.rate_limit_per_minute)

# 每个用户一把处理锁：保证同一用户的消息串行处理，
# 避免上一条还在检索/生成时下一条已开始（导致重复欢迎语、重复回复、会话错乱）。
_user_locks_guard = threading.Lock()
_user_locks: dict[str, threading.Lock] = {}


def _user_lock(wa_id: str) -> threading.Lock:
    with _user_locks_guard:
        lk = _user_locks.get(wa_id)
        if lk is None:
            lk = threading.Lock()
            _user_locks[wa_id] = lk
        return lk


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时确保向量库就绪，并预热 embedding 模型，避免第一条消息时才加载（耗时数十秒）
    ensure_collection()
    try:
        log.info("预热 embedding 模型 ...")
        embed_one("warmup")
        log.info("embedding 模型就绪")
    except Exception:
        log.exception("embedding 模型预热失败（将在首次请求时重试）")
    yield


app = FastAPI(title="WhatsApp 企业知识问答 Agent", lifespan=lifespan)


@app.get("/health")
def health():
    try:
        points = count_points()
        return {
            "status": "ok",
            "kb": {
                "collection": settings.qdrant_collection,
                "points": points,
                "accessible": True,
            },
        }
    except Exception as e:
        log.exception("健康检查失败")
        return {
            "status": "degraded",
            "kb": {"collection": settings.qdrant_collection, "accessible": False, "error": str(e)},
        }


class AskRequest(BaseModel):
    question: str


@app.post("/ask")
def ask_question(request: AskRequest):
    """直接问答接口，用于不带 Twilio 的调试。无会话状态。"""
    result = answer(request.question)
    return {
        "question": request.question,
        "answer": result.reply,
        "sources": result.sources,
        "status": result.status,
        "top_score": result.top_score,
    }


@app.post("/webhook")
async def webhook(request: Request, background_tasks: BackgroundTasks):
    form = await request.form()
    message_sid = form.get("MessageSid", "")
    from_ = form.get("From", "")
    body = (form.get("Body") or "").strip()

    # 同步幂等检查：必须在加入后台任务之前完成，避免 Twilio 快速重试时
    # 两个请求同时进入后台导致重复回复（FR-027）。
    if message_sid and idempotency.seen_or_mark(message_sid):
        log.info("重复投递已拦截 MessageSid=%s", message_sid)
        return PlainTextResponse("")

    # 立刻返回 200；处理全部放后台（宪法原则 II）。
    # 同一用户的处理在用户锁内串行，避免上一条还在检索时下一条已开始，
    # 导致重复欢迎语/重复回复/会话错乱。
    background_tasks.add_task(_handle_serialized, message_sid, from_, body)
    return PlainTextResponse("")


def _handle_serialized(message_sid: str, from_: str, body: str) -> None:
    """在按用户的锁内串行处理消息。"""
    if not from_:
        _handle(message_sid, from_, body)
        return
    with _user_lock(from_):
        _handle(message_sid, from_, body)


def _turns_to_messages(turns) -> list[dict]:
    return [{"role": t.role, "content": t.content} for t in turns]


def _send(to: str, text: str) -> None:
    try:
        send_whatsapp(to, text)
    except Exception:
        log.exception("发送 WhatsApp 回复失败 to=%s", mask_waid(to))


def _handle(message_sid: str, from_: str, body: str) -> None:
    request_id = new_request_id()
    waid_masked = mask_waid(from_)
    log_event(request_id, "message_received", from_=waid_masked, length=len(body), sid=message_sid)

    # 空消息安全忽略
    if not from_ or not body:
        return

    # 注意：幂等检查已在 webhook 同步阶段完成，这里不再重复。

    # 长度校验（FR-026）
    if not check_message_length(body, settings.message_max_chars):
        log_event(request_id, "message_too_long", from_=waid_masked)
        _send(from_, responses.MESSAGE_TOO_LONG)
        return

    # 限流（FR-025）
    if not rate_limiter.allow(from_):
        log_event(request_id, "rate_limited", from_=waid_masked)
        _send(from_, responses.RATE_LIMITED)
        return

    # 指令识别
    cmd = parse_command(body)
    if cmd is not None:
        _handle_command(request_id, from_, body, cmd.type, cmd.value)
        return

    # 会话状态：新用户欢迎 / 过期提示。
    # 问候语已在指令阶段处理（只寒暄不问答），不会走到这里。
    state = session_store.state(from_)
    if state == "absent":
        _send(from_, responses.WELCOME)
    elif state == "expired":
        _send(from_, responses.SESSION_RESTARTED)

    # 正常问答
    _answer_question(request_id, from_, body)


def _handle_command(request_id: str, from_: str, body: str, cmd_type: str, value: str) -> None:
    if cmd_type == "help":
        _send(from_, responses.HELP)
    elif cmd_type == "reset":
        session_store.reset(from_)
        _send(from_, responses.RESET_DONE)
    elif cmd_type == "handoff":
        _do_handoff(request_id, from_, body, reason="customer_request")
    elif cmd_type == "feedback":
        accepted = session_store.try_mark_feedback(from_, value)
        if accepted:
            log_event(request_id, "feedback", from_=mask_waid(from_), rating=value)
        _send(from_, responses.THANKS_FEEDBACK)
    elif cmd_type == "greeting":
        # 纯问候：新用户给完整欢迎语，老用户简单寒暄，不做 RAG。
        # 记录这一轮，确保后续消息不再被当成新用户重复欢迎。
        if session_store.exists(from_):
            greeting_reply = "你好！有什么可以帮你的吗？直接提问即可。"
        else:
            greeting_reply = responses.WELCOME
        session_store.add_turn(from_, "user", body)
        session_store.add_turn(from_, "assistant", greeting_reply)
        _send(from_, greeting_reply)


def _do_handoff(request_id: str, from_: str, question: str, reason: str) -> None:
    ok = trigger_handoff(session_store, from_, question, reason=reason)
    log_event(request_id, "handoff", from_=mask_waid(from_), reason=reason, notified=ok)
    _send(from_, responses.HANDOFF_NOTIFIED if ok else responses.HANDOFF_UNAVAILABLE)


def _answer_question(request_id: str, from_: str, body: str) -> None:
    try:
        # 取历史（已按轮数/字符截断）
        turns, _ = session_store.build_context(from_)
        history = _turns_to_messages(turns)

        result = answer(body, history=history)
        log_event(
            request_id,
            "answer_done",
            from_=mask_waid(from_),
            status=result.status,
            hits=len(result.sources),
            top_score=round(result.top_score, 3) if result.top_score is not None else None,
        )

        if result.status == "empty_kb":
            _send(from_, responses.EMPTY_KB)
            return

        if result.status == "no_match":
            session_store.add_turn(from_, "user", body)
            session_store.add_turn(from_, "assistant", responses.NO_ANSWER)
            streak = session_store.record_miss(from_)
            if streak >= 2:
                # 连续 2 次答不出，自动转人工（FR-016）
                _send(from_, responses.NO_ANSWER)
                _do_handoff(request_id, from_, body, reason="auto_no_answer")
            else:
                _send(from_, responses.NO_ANSWER)
            return

        # 正常回答
        session_store.record_hit(from_)
        reply = result.reply
        if result.sources:
            reply += "\n\n参考来源: " + ", ".join(result.sources)
        reply = responses.with_feedback_hint(reply)

        session_store.add_turn(from_, "user", body)
        session_store.add_turn(from_, "assistant", result.reply)
        _send(from_, reply)

    except Exception:
        log.exception("问答处理失败 request_id=%s", request_id)
        _send(from_, responses.ERROR)


@app.post("/admin/ingest")
def admin_ingest():
    """在服务运行中重新导入知识库（全量重建，无需停服）。"""
    total = ingest_directory(str(SAMPLE_DOCS_DIR), rebuild=True)
    return {"ingested_chunks": total}
