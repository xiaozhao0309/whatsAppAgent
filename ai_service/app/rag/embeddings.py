"""文本向量化（embedding）。

用 sentence-transformers 的本地小模型 all-MiniLM-L6-v2，不需要任何 API Key，
首次运行会自动下载模型（约 80MB）。输出维度 384，归一化后用余弦相似度检索。
"""
import functools

from sentence_transformers import SentenceTransformer

MODEL_NAME = "all-MiniLM-L6-v2"
EMBEDDING_DIM = 384  # 该模型输出维度，建 Qdrant collection 时要一致


@functools.lru_cache(maxsize=1)
def _model() -> SentenceTransformer:
    # lru_cache 保证全局只加载一次模型（模型加载较慢）
    return SentenceTransformer(MODEL_NAME)


def embed(texts: list[str]) -> list[list[float]]:
    """批量向量化。"""
    return _model().encode(texts, normalize_embeddings=True).tolist()


def embed_one(text: str) -> list[float]:
    """单条向量化。"""
    return embed([text])[0]
