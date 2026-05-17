#!/usr/bin/env python3
"""Inject sample data from tests/sample_data/ into the vector store for demos.

Usage:
    python -m scripts.inject_sample
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

from memory_mcp.config import Config
from memory_mcp import (
    ChunkInput,
    Database,
    store_memory_atomic,
)
from memory_mcp.embeddings import OllamaEmbeddingClient

_cfg = Config.load_cached()
DB_PATH = _cfg.storage.db_path
OLLAMA_URL = _cfg.server.ollama_base_url
OLLAMA_MODEL = _cfg.embedding.model


def main() -> None:
    repo_root = Path(__file__).resolve().parent.parent
    sample_dir = repo_root / "tests" / "sample_data"

    print("=== MengPo Sample Injection ===")
    print(f"  DB:     {DB_PATH}")
    print(f"  Source: {sample_dir}")

    if not sample_dir.is_dir():
        print(f"  ERROR: sample_data not found at {sample_dir}")
        sys.exit(1)

    db = Database(DB_PATH)
    ec = OllamaEmbeddingClient(base_url=OLLAMA_URL, model=OLLAMA_MODEL)

    files = sorted(sample_dir.glob("*.md"))
    total = 0

    for fp in files:
        content = fp.read_text(encoding="utf-8")
        source_file = fp.name

        # Simple paragraph chunking.
        paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()]
        for ci, para in enumerate(paragraphs):
            if len(para) < 10:
                continue

            vec = ec.embed(para)
            store_memory_atomic(
                db,
                namespace="sample",
                content=para,
                content_hash=hashlib.sha256(para.encode("utf-8")).hexdigest(),
                chunks=[
                    ChunkInput(
                        content=para,
                        embedding=json.dumps(vec, separators=(",", ":")).encode("utf-8"),
                        chunk_index=ci,
                    )
                ],
                source_file=source_file,
            )
            total += 1

    counts = db.row_counts()
    print(f"  Files:      {len(files)}")
    print(f"  Chunks:     {total}")
    print(f"  DB now:     {counts['memories']} memories, {counts['chunks_meta']} meta, "
          f"{counts['chunks_vec']} vec")
    print(f"\n  Next: python -m memory_mcp.server  (or scripts/bridge.py)")
    db.close()


if __name__ == "__main__":
    main()
