"""One-time bulk import of the sample knowledge base into Qdrant.

Run from the ai_service/ directory:
    python scripts/ingest.py

Note: Qdrant local-file mode allows only one process at a time. Stop the
AI service first, or use POST /ingest on the running service instead.
"""
import sys
from pathlib import Path

# Make the `app` package importable.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.rag.ingest import ingest_directory  # noqa: E402


if __name__ == "__main__":
    docs_dir = Path(__file__).resolve().parent.parent / "app" / "sample_docs"
    print(f"Importing documents from: {docs_dir}")
    total = ingest_directory(str(docs_dir))
    print(f"\nDone. Imported {total} chunks.")
