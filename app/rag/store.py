"""Qdrant 向量库封装（本地文件模式，无需单独部署服务）。

一个 collection 存所有知识切片；每条 point 的 payload 里放原文和来源文件名。
"""
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

from ..config import settings
from .embeddings import EMBEDDING_DIM

_client: QdrantClient | None = None


def get_client() -> QdrantClient:
    """全局单例 client。Qdrant 本地模式同一进程只能有一个 client 持锁。"""
    global _client
    if _client is None:
        _client = QdrantClient(path=settings.qdrant_path)
    return _client


def ensure_collection() -> None:
    """如果 collection 不存在就建一个。"""
    client = get_client()
    names = [c.name for c in client.get_collections().collections]
    if settings.qdrant_collection not in names:
        client.create_collection(
            collection_name=settings.qdrant_collection,
            vectors_config=VectorParams(size=EMBEDDING_DIM, distance=Distance.COSINE),
        )


def upsert_points(points: list[PointStruct]) -> None:
    """批量写入/覆盖切片。"""
    get_client().upsert(collection_name=settings.qdrant_collection, points=points)


def search(query_vector: list[float], limit: int):
    """向量检索，返回 top-k 的 ScoredPoint 列表。"""
    return get_client().query_points(
        collection_name=settings.qdrant_collection,
        query=query_vector,
        limit=limit,
        with_payload=True,
    ).points


def count_points() -> int:
    """返回 collection 当前的 point 数量；collection 不存在时返回 0。"""
    client = get_client()
    names = [c.name for c in client.get_collections().collections]
    if settings.qdrant_collection not in names:
        return 0
    return client.count(collection_name=settings.qdrant_collection).count


def clear_collection() -> None:
    """清空 collection 内全部 point（用于全量重建）。

    删除后重建一个空 collection，保证向量维度配置一致。
    """
    client = get_client()
    names = [c.name for c in client.get_collections().collections]
    if settings.qdrant_collection in names:
        client.delete_collection(collection_name=settings.qdrant_collection)
    ensure_collection()
