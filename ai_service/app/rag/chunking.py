"""把长文档切成小块（chunk），这是 RAG 的第一步。

切得太小丢上下文，太大检索不精准。这里先按段落切，超长的段落再按固定长度 + 重叠切。
"""


def chunk_text(text: str, size: int = 800, overlap: int = 100) -> list[str]:
    chunks: list[str] = []
    # 先按空行切成段落
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    for para in paragraphs:
        if len(para) <= size:
            chunks.append(para)
            continue
        # 段落太长：按 size 滑窗切，带 overlap 保证不切断语义
        start = 0
        while start < len(para):
            end = start + size
            chunks.append(para[start:end])
            start = end - overlap
    return [c for c in chunks if c.strip()]
