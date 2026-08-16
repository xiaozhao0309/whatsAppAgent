"""知识库入库：读目录下的文档 -> 切片 -> 向量化 -> 写入 Qdrant。

1.0 采用全量重建：导入前先清空 collection，避免新旧内容混杂。
"""
import hashlib
from pathlib import Path

from qdrant_client.models import PointStruct

from ..config import settings
from .chunking import chunk_text
from .embeddings import embed
from .store import clear_collection, ensure_collection, upsert_points


def _point_id(source: str, index: int) -> int:
    """根据"来源 + 序号"生成稳定 id，重复入库会覆盖而不是累积重复。"""
    h = hashlib.sha1(f"{source}:{index}".encode()).hexdigest()
    return int(h[:15], 16)


def ingest_file(path: Path) -> int:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        # 读取失败要明确报错，不静默跳过（FR-008）
        raise RuntimeError(f"无法读取文档 {path.name}: {e}") from e

    chunks = chunk_text(text, size=settings.chunk_size, overlap=settings.chunk_overlap)
    if not chunks:
        return 0
    vectors = embed(chunks)
    points = [
        PointStruct(
            id=_point_id(path.name, i),
            vector=vectors[i],
            payload={
                "text": chunks[i],
                "source": path.name,
                "chunk_index": i,
            },
        )
        for i in range(len(chunks))
    ]
    upsert_points(points)
    return len(chunks)


def ingest_directory(dir_path: str, *, rebuild: bool = True) -> int:
    """导入目录下所有 .md / .txt 文件，返回总切片数。

    rebuild=True 时先清空旧 collection（全量重建，FR-008）。
    """
    if rebuild:
        clear_collection()
    else:
        ensure_collection()

    d = Path(dir_path)
    if not d.exists():
        raise FileNotFoundError(f"文档目录不存在: {dir_path}")

    files = sorted(d.glob("*.md")) + sorted(d.glob("*.txt"))
    if not files:
        print(f"  目录 {dir_path} 下没有 .md/.txt 文档")
        return 0

    total = 0
    failed = 0
    for f in files:
        try:
            n = ingest_file(f)
            print(f"  {f.name}: {n} 个切片")
            total += n
        except RuntimeError as e:
            failed += 1
            print(f"  [失败] {e}")

    if failed:
        raise RuntimeError(f"{failed} 个文档导入失败")
    if total == 0:
        raise RuntimeError("所有文档均为空，未导入任何切片")
    return total
