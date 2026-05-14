#!/usr/bin/env python3
"""MengPo memory injection — scan markdown files and ingest into the vector store.

Usage:
    python -m scripts.inject_memory
    python scripts/inject_memory.py

Environment variables:
    MENGPO_DB_PATH       — SQLite database path (default: ./mengpo_memory.db)
    MENGPO_MEMORY_DIR    — directory to scan for markdown files
    MENGPO_CHUNK_SIZE    — paragraph chunk size in characters (default: 500)
    MENGPO_OLLAMA_URL    — Ollama base URL (default: http://127.0.0.1:11434)
    MENGPO_OLLAMA_MODEL  — embedding model name (default: qwen3-embedding-0.6b)
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

# Allow running from repo root without installing the package.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from memory_mcp import (
    ChunkInput,
    Database,
    store_memory_atomic,
)
from memory_mcp.embeddings import OllamaEmbeddingClient, EmbeddingError

# ── Configuration ──────────────────────────────────────────────────────────

DB_PATH = os.getenv("MENGPO_DB_PATH", str(Path.cwd() / "mengpo_memory.db"))
MEMORY_DIR = os.getenv("MENGPO_MEMORY_DIR", str(Path.cwd() / "memory"))
CHUNK_SIZE = int(os.getenv("MENGPO_CHUNK_SIZE", "500"))
OLLAMA_URL = os.getenv("MENGPO_OLLAMA_URL", "http://127.0.0.1:11434")
OLLAMA_MODEL = os.getenv("MENGPO_OLLAMA_MODEL", "qwen3-embedding-0.6b")


# ── Chunking ───────────────────────────────────────────────────────────────

def chunk_text(text: str, max_size: int = CHUNK_SIZE) -> list[str]:
    """Split text on paragraph boundaries, respecting max_size.

    Paragraphs shorter than *max_size* are kept intact.  Longer paragraphs
    are sliced into *max_size*-character windows.
    """
    chunks: list[str] = []
    for paragraph in text.split("\n\n"):
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        if len(paragraph) <= max_size:
            chunks.append(paragraph)
        else:
            for i in range(0, len(paragraph), max_size):
                chunks.append(paragraph[i : i + max_size])
    return chunks


# ── Dedup helper ───────────────────────────────────────────────────────────

def _chunk_already_stored(db: Database, source_file: str, chunk_index: int) -> bool:
    """Return True when a (source_file, chunk_index) pair already exists."""
    row = db.conn.execute(
        "SELECT 1 FROM chunks_meta WHERE source_file = ? AND chunk_index = ? LIMIT 1",
        (source_file, chunk_index),
    ).fetchone()
    return row is not None


# ── File scanner ───────────────────────────────────────────────────────────

def scan_markdown_files(root: str | Path) -> list[Path]:
    """Recursively collect ``*.md`` files under *root*."""
    root_path = Path(root).expanduser().resolve()
    if not root_path.is_dir():
        raise FileNotFoundError(f"Memory directory not found: {root_path}")
    return sorted(root_path.rglob("*.md"))


# ── Main ───────────────────────────────────────────────────────────────────

def main() -> None:
    print("=== MengPo Memory Injection ===")
    print(f"  DB:        {DB_PATH}")
    print(f"  Memory dir: {MEMORY_DIR}")
    print(f"  Chunk size: {CHUNK_SIZE} chars")
    print(f"  Ollama:    {OLLAMA_URL} / {OLLAMA_MODEL}")

    db = Database(DB_PATH)
    ec = OllamaEmbeddingClient(base_url=OLLAMA_URL, model=OLLAMA_MODEL)

    files = scan_markdown_files(MEMORY_DIR)
    print(f"  Files:      {len(files)}")

    total = 0
    skipped = 0
    for fp in files:
        # Derive a relative path for stable source_file dedup.
        try:
            source_file = str(fp.relative_to(Path(MEMORY_DIR).resolve()))
        except ValueError:
            source_file = fp.name

        try:
            content = fp.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            print(f"  [skip] {source_file}: read error ({exc})")
            skipped += 1
            continue

        chunks = chunk_text(content)
        if not chunks:
            continue

        for ci, chunk_content in enumerate(chunks):
            if len(chunk_content.strip()) < 10:
                continue

            # Idempotency: skip chunks already in the database.
            if _chunk_already_stored(db, source_file, ci):
                skipped += 1
                continue

            # Embedding — fail fast on network / model errors.
            try:
                vec = ec.embed(chunk_content)
            except EmbeddingError as exc:
                print(f"  [fail] {source_file} chunk {ci}: embedding error ({exc})")
                skipped += 1
                continue

            # Atomic write across memories / chunks_vec / chunks_meta.
            try:
                store_memory_atomic(
                    db,
                    namespace="default",
                    content=chunk_content,
                    content_hash=hashlib.sha256(chunk_content.encode("utf-8")).hexdigest(),
                    chunks=[
                        ChunkInput(
                            content=chunk_content,
                            embedding=json.dumps(vec, separators=(",", ":")).encode("utf-8"),
                            chunk_index=ci,
                        )
                    ],
                    source_file=source_file,
                )
            except Exception as exc:
                print(f"  [fail] {source_file} chunk {ci}: store error ({exc})")
                skipped += 1
                continue

            total += 1

        if total > 0 and total % 100 == 0:
            print(f"  {total} chunks...")

    print(f"  Total:   {total} chunks injected")
    print(f"  Skipped: {skipped} chunks (already present or errored)")
    counts = db.row_counts()
    print(f"  DB now:  {counts['memories']} memories, {counts['chunks_meta']} meta, "
          f"{counts['chunks_vec']} vec")

    db.close()


if __name__ == "__main__":
    main()
