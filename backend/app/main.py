"""Backend entry point: receives Twilio WhatsApp webhooks and orchestrates replies.

Flow: Twilio POSTs a user message to /webhook -> return 200 immediately
(avoid timeout retries) -> in a background task, call the AI/RAG service over
HTTP -> send the answer back via the Twilio REST API.

Single instance, single worker: sessions/idempotency/rate limits are in-process.
"""
import logging
import threading
from contextlib import asynccontextmanager

from fastapi import BackgroundTasks, FastAPI, Request
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from . import responses
from .channel import send_whatsapp
from .commands import parse_command
from .config import settings
from .guards import IdempotencyGuard, RateLimiter, check_message_length
from .handoff import trigger_handoff
from .handoff_policy import decide
from .handoff_store import HandoffStore
from .observability import log_event, mask_waid, new_request_id
from .rag_client import RAGClient, RAGServiceError
from .session import SessionStore

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("whatsapp_agent")

# In-process shared components (single worker).
session_store = SessionStore(
    ttl_seconds=settings.session_ttl_seconds,
    max_turns=settings.session_max_turns,
    max_chars=settings.session_max_chars,
)
idempotency = IdempotencyGuard()
rate_limiter = RateLimiter(max_per_minute=settings.rate_limit_per_minute)
rag_client = RAGClient(base_url=settings.rag_service_url, timeout=settings.rag_timeout)
# Tracks which sessions have already been handed off to a human, so repeated
# failures don't spam the on-duty number. Also the seam for future bidirectional
# staff<->customer relay.
handoff_store = HandoffStore(ttl_seconds=settings.session_ttl_seconds)

# One processing lock per user so one user's messages are handled serially,
# preventing duplicate welcomes/replies/session corruption when a previous
# message is still being processed.
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
    # The AI/RAG service owns the embedding model and Qdrant; the backend just
    # checks it is reachable at startup.
    try:
        rag_client.health()
        log.info("AI/RAG service reachable at %s", settings.rag_service_url)
    except RAGServiceError:
        log.warning(
            "AI/RAG service not reachable at startup (%s); will retry per request",
            settings.rag_service_url,
        )
    yield


app = FastAPI(title="WhatsApp Agent - Backend", lifespan=lifespan)


@app.get("/health")
def health():
    result = {"status": "ok", "ai_service": None}
    try:
        ai = rag_client.health()
        result["ai_service"] = ai
        if ai.get("status") != "ok":
            result["status"] = "degraded"
    except RAGServiceError as e:
        result["status"] = "degraded"
        result["ai_service"] = {"reachable": False, "error": str(e)}
    return result


class AskRequest(BaseModel):
    question: str


@app.post("/ask")
def ask_question(request: AskRequest):
    """Direct Q&A endpoint for debugging without Twilio. No session state."""
    try:
        result = rag_client.answer(request.question)
    except RAGServiceError as e:
        return {
            "question": request.question,
            "answer": responses.ERROR,
            "sources": [],
            "status": "error",
            "top_score": None,
            "error": str(e),
        }
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

    # Synchronous idempotency: must run before scheduling the background task
    # so Twilio fast retries cannot enqueue duplicate handlers (FR-027).
    if message_sid and idempotency.seen_or_mark(message_sid):
        log.info("duplicate delivery ignored MessageSid=%s", message_sid)
        return PlainTextResponse("")

    # Return 200 immediately; all work happens in the background (constitution II).
    # One user's messages are serialized via the per-user lock.
    background_tasks.add_task(_handle_serialized, message_sid, from_, body)
    return PlainTextResponse("")


def _handle_serialized(message_sid: str, from_: str, body: str) -> None:
    """Handle a message while holding that user's lock."""
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
        log.exception("failed to send WhatsApp reply to=%s", mask_waid(to))


def _handle(message_sid: str, from_: str, body: str) -> None:
    request_id = new_request_id()
    waid_masked = mask_waid(from_)
    log_event(request_id, "message_received", from_=waid_masked, length=len(body), sid=message_sid)

    # Safely ignore empty messages.
    if not from_ or not body:
        return

    # Idempotency already ran synchronously in the webhook; don't repeat it here.

    # Length check (FR-026).
    if not check_message_length(body, settings.message_max_chars):
        log_event(request_id, "message_too_long", from_=waid_masked)
        _send(from_, responses.MESSAGE_TOO_LONG)
        return

    # Rate limiting (FR-025).
    if not rate_limiter.allow(from_):
        log_event(request_id, "rate_limited", from_=waid_masked)
        _send(from_, responses.RATE_LIMITED)
        return

    # Command recognition.
    cmd = parse_command(body)
    if cmd is not None:
        _handle_command(request_id, from_, body, cmd.type, cmd.value)
        return

    # Session state: welcome new users / restart after expiry.
    # Greetings are handled as commands above and never reach RAG.
    state = session_store.state(from_)
    if state == "absent":
        _send(from_, responses.WELCOME)
    elif state == "expired":
        _send(from_, responses.SESSION_RESTARTED)

    # Normal Q&A.
    _answer_question(request_id, from_, body)


def _handle_command(request_id: str, from_: str, body: str, cmd_type: str, value: str) -> None:
    if cmd_type == "help":
        _send(from_, responses.HELP)
    elif cmd_type == "reset":
        session_store.reset(from_)
        handoff_store.clear(from_)
        _send(from_, responses.RESET_DONE)
    elif cmd_type == "handoff":
        _do_customer_handoff(request_id, from_, body)
    elif cmd_type == "feedback":
        accepted = session_store.try_mark_feedback(from_, value)
        if accepted:
            log_event(request_id, "feedback", from_=mask_waid(from_), rating=value)
        _send(from_, responses.THANKS_FEEDBACK)
    elif cmd_type == "greeting":
        # Pure greeting: full welcome for new users, brief hello for existing
        # ones. Record the turn so later messages aren't re-welcomed. No RAG.
        if session_store.exists(from_):
            greeting_reply = "Hi! How can I help? Just send your question."
        else:
            greeting_reply = responses.WELCOME
        session_store.add_turn(from_, "user", body)
        session_store.add_turn(from_, "assistant", greeting_reply)
        _send(from_, greeting_reply)


def _notify_handoff(request_id: str, from_: str, question: str, reason: str) -> bool:
    """Send the hand-off notification to on-duty staff. Returns whether notified."""
    ok = trigger_handoff(session_store, from_, question, reason=reason)
    log_event(request_id, "handoff", from_=mask_waid(from_), reason=reason, notified=ok)
    return ok


def _do_customer_handoff(request_id: str, from_: str, body: str) -> None:
    """Customer asked for a human: reply with the contact phone number and, if
    configured, also notify the on-duty staff on WhatsApp (best effort)."""
    ok = _notify_handoff(request_id, from_, body, reason="customer_request")
    handoff_store.mark_active(from_, reason="customer_request", notified=ok)
    _send(from_, responses.CONTACT_HUMAN.format(phone=settings.contact_phone_number))


def _answer_question(request_id: str, from_: str, body: str) -> None:
    try:
        status, top_score, result = _call_ai(request_id, from_, body)

        log_event(
            request_id,
            "answer_done",
            from_=mask_waid(from_),
            status=status,
            hits=len(result.sources) if result else 0,
            top_score=round(top_score, 3) if top_score is not None else None,
        )

        decision = decide(
            status=status,
            top_score=top_score,
            miss_streak=session_store.get_miss_streak(from_),
            error_streak=session_store.get_error_streak(from_),
            already_active=handoff_store.is_active(from_),
            miss_threshold=settings.handoff_miss_threshold,
            error_threshold=settings.handoff_error_threshold,
            low_conf_min=settings.low_confidence_score,
        )

        if decision.record_hit:
            session_store.record_hit(from_)
        if decision.record_miss:
            session_store.record_miss(from_)
        if decision.record_error:
            session_store.record_error(from_)

        # Repeated no_match/error: give the customer the contact phone number
        # once (no auto staff notification), and mark escalated so later
        # failures don't repeat the number.
        customer_reply = decision.customer_reply
        if decision.mark_escalated:
            handoff_store.mark_active(
                from_, reason="auto_escalated", notified=False
            )
            customer_reply = customer_reply.format(
                phone=settings.contact_phone_number
            )

        if decision.record_hit:
            # Successful (or low-confidence) answer.
            reply = result.reply
            if result.sources:
                reply += "\n\nSources: " + ", ".join(result.sources)
            if decision.low_confidence:
                reply += responses.LOW_CONFIDENCE_HINT
            reply = responses.with_feedback_hint(reply)
            session_store.add_turn(from_, "user", body)
            session_store.add_turn(from_, "assistant", result.reply)
            _send(from_, reply)
        else:
            session_store.add_turn(from_, "user", body)
            session_store.add_turn(from_, "assistant", customer_reply)
            _send(from_, customer_reply)
    except Exception:
        # Last-resort safety net: never let a handler crash without replying.
        log.exception("answer handling failed request_id=%s", request_id)
        _send(from_, responses.ERROR)


def _call_ai(request_id: str, from_: str, body: str):
    """Call the AI service. Returns (status, top_score, result).

    Connection/timeout/5xx become status="error" instead of propagating, so the
    hand-off policy can escalate repeated AI failures to a human.
    """
    try:
        # History is already truncated by turn count / char count.
        turns, _ = session_store.build_context(from_)
        history = _turns_to_messages(turns)
        result = rag_client.answer(body, history=history)
        return result.status, result.top_score, result
    except RAGServiceError:
        log.exception("AI/RAG service call failed request_id=%s", request_id)
        return "error", None, None


@app.post("/admin/ingest")
def admin_ingest():
    """Rebuild the knowledge base via the AI service (no need to stop it)."""
    total = rag_client.ingest()
    return {"ingested_chunks": total}
