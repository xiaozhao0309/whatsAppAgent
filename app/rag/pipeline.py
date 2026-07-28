"""RAG 主流程（"算法"部分）：检索 + 生成。

answer(question) -> (答案, 来源列表)
"""
from openai import OpenAI

from ..config import settings
from .embeddings import embed_one
from .store import search

SYSTEM_PROMPT = """你是一个企业内部知识问答助手。请只根据下面提供的【参考资料】回答用户问题。
要求：
1. 答案简洁、准确，尽量直接给出可操作的信息。
2. 如果参考资料里没有相关信息，明确说"资料里没有相关内容"，不要编造。
3. 回答末尾用 [来源: 文件名] 标注引用的资料来源（没有则不标）。"""


def _build_prompt(question: str, context: str) -> str:
    return f"""【参考资料】
{context}

【用户问题】
{question}"""


def answer(question: str) -> tuple[str, list[str]]:
    # 1. 检索：把问题向量化，在 Qdrant 里找最相关的 top_k 段
    qvec = embed_one(question)
    hits = search(qvec, limit=settings.top_k)

    # 知识库为空时的兜底
    if not hits:
        return "知识库还是空的，请先导入文档（运行 `python scripts/ingest.py` 或调用 /admin/ingest）。", []

    # 2. 拼接上下文，同时记录命中的来源
    context_parts: list[str] = []
    sources: list[str] = []
    for i, h in enumerate(hits, 1):
        payload = h.payload or {}
        text = payload.get("text", "")
        source = payload.get("source", "未知")
        context_parts.append(f"[{i}] (来源: {source})\n{text}")
        if source not in sources:
            sources.append(source)

    # 3. 生成：把检索到的资料塞进 prompt，让 Claude 回答
    if not settings.ark_api_key:
        raise RuntimeError("ARK_API_KEY 未配置")

    if not settings.ark_model:
        raise RuntimeError("ARK_MODEL 未配置")

    client = OpenAI(
        api_key=settings.ark_api_key,
        base_url=settings.ark_base_url,
    )

    resp = client.chat.completions.create(
        model=settings.ark_model,
        max_tokens=1024,
        messages=[
            {
                "role": "system",
                "content": SYSTEM_PROMPT,
            },
            {
                "role": "user",
                "content": _build_prompt(
                    question,
                    "\n\n".join(context_parts),
                ),
            },
        ],
    )

    reply = (resp.choices[0].message.content or "").strip()
    return reply, sources
