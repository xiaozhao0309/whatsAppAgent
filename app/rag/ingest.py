"""知识库入库：读目录下的文档 -> 切片 -> 向量化 -> 写入 Qdrant。"""
import hashlib
from pathlib import Path

from qdrant_client.models import PointStruct

from ..config import settings
from .chunking import chunk_text
from .embeddings import embed
from .store import ensure_collection, upsert_points


def _point_id(source: str, index: int) -> int:
    """根据"来源 + 序号"生成稳定 id，重复入库会覆盖而不是累积重复。"""
    h = hashlib.sha1(f"{source}:{index}".encode()).hexdigest()
    return int(h[:15], 16)


def ingest_file(path: Path) -> int:
    text = path.read_text(encoding="utf-8")
    chunks = chunk_text(text, size=settings.chunk_size, overlap=settings.chunk_overlap)
    if not chunks:
        return 0
    vectors = embed(chunks)
    points = [
        PointStruct(
            id=_point_id(path.name, i),
            vector=vectors[i],
            payload={"text": chunks[i], "source": path.name},
        )
        for i in range(len(chunks))
    ]
    upsert_points(points)
    return len(chunks)


def ingest_directory(dir_path: str) -> int:
    """导入目录下所有 .md / .txt 文件，返回总切片数。"""
    ensure_collection()
    d = Path(dir_path)
    files = sorted(d.glob("*.md")) + sorted(d.glob("*.txt"))
    total = 0
    for f in files:
        n = ingest_file(f)
        print(f"  {f.name}: {n} 个切片")
        total += n
    return total
