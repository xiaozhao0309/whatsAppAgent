"""一键导入示例知识库到 Qdrant。

用法（在项目根目录执行）:
    python scripts/ingest.py

注意：Qdrant 本地文件模式同一时间只能被一个进程打开。
若 FastAPI 服务正在运行，请先停掉再跑本脚本，或改用 POST /admin/ingest 接口。
"""
import sys
from pathlib import Path

# 让脚本能 import 到 app 包
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.rag.ingest import ingest_directory  # noqa: E402


if __name__ == "__main__":
    docs_dir = Path(__file__).resolve().parent.parent / "app" / "sample_docs"
    print(f"开始导入: {docs_dir}")
    total = ingest_directory(str(docs_dir))
    print(f"\n完成，共导入 {total} 个切片。")
