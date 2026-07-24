"""FastAPI 入口：接收 Twilio 的 WhatsApp webhook，触发 RAG 问答。

流程：Twilio 把用户消息 POST 到 /webhook -> 立刻回 200（避免超时重试）
-> 在后台跑 RAG -> 用 Twilio REST API 把答案发回用户。
"""
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, Request
from fastapi.responses import PlainTextResponse

from .channel import send_whatsapp
from .rag.pipeline import answer
from .rag.store import ensure_collection

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("whatsapp_agent")

SAMPLE_DOCS_DIR = Path(__file__).resolve().parent / "sample_docs"


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时确保 Qdrant collection 存在
    ensure_collection()
    yield


app = FastAPI(title="WhatsApp 企业知识问答 Agent", lifespan=lifespan)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/webhook")
async def webhook(request: Request, background_tasks: BackgroundTasks):
    # Twilio 用 form 表单提交，不是 JSON
    form = await request.form()
    from_ = form.get("From", "")           # 形如 whatsapp:+8613...
    body = (form.get("Body") or "").strip()

    log.info("收到消息 from=%s body=%r", from_, body)
    if from_ and body:
        # 放后台处理，立刻返回 200；RAG 慢也不会被 Twilio 当超时重试
        background_tasks.add_task(_handle, from_, body)
    return PlainTextResponse("")  # 空 200


def _handle(from_: str, body: str) -> None:
    try:
        reply, sources = answer(body)
        text = reply
        if sources:
            text += "\n\n参考来源: " + ", ".join(sources)
    except Exception as e:
        log.exception("问答处理失败")
        text = f"抱歉，处理时出错了：{e}"
    try:
        send_whatsapp(from_, text)
    except Exception:
        log.exception("发送回复失败")


@app.post("/admin/ingest")
def admin_ingest():
    """在服务运行中重新导入知识库（无需停服跑脚本）。"""
    from .rag.ingest import ingest_directory

    total = ingest_directory(str(SAMPLE_DOCS_DIR))
    return {"ingested_chunks": total}
