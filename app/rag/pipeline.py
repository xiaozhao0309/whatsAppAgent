"""RAG 主流程（"算法"部分）：检索 + 生成。

answer(question, history) -> AnswerResult
- 检索相关片段，按相似度阈值判断是否值得回答
- 低于阈值或知识库为空时直接拒答，不调用 LLM
- 支持多轮历史（以 OpenAI 兼容的 messages 格式传入）
- 回答长度受控，带来源
"""
from dataclasses import dataclass, field

from openai import OpenAI

from ..config import settings
from .embeddings import embed_one
from .store import count_points, search

SYSTEM_PROMPT = """你是一个企业内部知识问答助手。请只根据下面提供的【参考资料】回答用户问题。
要求：
1. 答案简洁、准确，尽量直接给出可操作的信息，不要超过 800 字。
2. 如果参考资料里没有相关信息，明确说"资料里没有相关内容"，不要编造。
3. 回答末尾用 [来源: 文件名] 标注引用的资料来源（多个来源全部列出，没有则不标）。"""

REFUSAL = "资料里没有相关内容"


@dataclass
class AnswerResult:
    reply: str
    sources: list[str] = field(default_factory=list)
    status: str = "answered"  # answered | no_match | empty_kb | error
    top_score: float | None = None
    need_handoff: bool = False


def _build_context(hits) -> tuple[str, list[str], float | None]:
    parts: list[str] = []
    sources: list[str] = []
    top_score: float | None = None
    for i, h in enumerate(hits, 1):
        payload = h.payload or {}
        text = payload.get("text", "")
        source = payload.get("source", "未知")
        parts.append(f"[{i}] (来源: {source})\n{text}")
        if source not in sources:
            sources.append(source)
        if top_score is None or (h.score is not None and h.score > top_score):
            top_score = h.score
    return "\n\n".join(parts), sources, top_score


def _truncate(text: str, max_chars: int) -> str:
    text = text.strip()
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1].rstrip() + "…"


def answer(question: str, history: list | None = None) -> AnswerResult:
    # 1. 知识库为空时的兜底
    if count_points() == 0:
        return AnswerResult(reply="", status="empty_kb")

    # 2. 检索
    qvec = embed_one(question)
    hits = search(qvec, limit=settings.top_k)
    if not hits:
        return AnswerResult(reply="", status="no_match")

    context, sources, top_score = _build_context(hits)

    # 3. 相关性阈值：低于阈值直接拒答，不调用 LLM（FR-002）
    if top_score is not None and top_score < settings.rag_score_threshold:
        return AnswerResult(
            reply="", sources=sources, status="no_match", top_score=top_score
        )

    # 4. 构造多轮 messages（FR-009/011/012：历史已在调用前截断）
    if not settings.ark_api_key:
        raise RuntimeError("ARK_API_KEY 未配置")
    if not settings.ark_model:
        raise RuntimeError("ARK_MODEL 未配置")

    messages = [
        {"role": "system", "content": f"{SYSTEM_PROMPT}\n\n【参考资料】\n{context}"},
    ]
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": question})

    client = OpenAI(api_key=settings.ark_api_key, base_url=settings.ark_base_url)
    resp = client.chat.completions.create(
        model=settings.ark_model,
        max_tokens=1024,
        messages=messages,
    )
    reply = (resp.choices[0].message.content or "").strip()

    # 5. 模型自陈无相关内容，也按拒答处理
    if not reply or REFUSAL in reply:
        return AnswerResult(
            reply="", sources=sources, status="no_match", top_score=top_score
        )

    reply = _truncate(reply, settings.answer_max_chars)
    return AnswerResult(reply=reply, sources=sources, status="answered", top_score=top_score)
