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
from dataclasses import dataclass
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
BATCH_SIZE = int(os.getenv("MENGPO_BATCH_SIZE", "15"))
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


# ── Dedup & incremental update ────────────────────────────────────────────

@dataclass
class ExistingChunk:
    memory_id: int
    content_hash: str


def _lookup_existing(db: Database, source_file: str, chunk_index: int) -> ExistingChunk | None:
    """Return the existing (memory_id, content_hash) for a chunk, or None.

    Only considers non-deleted memories — soft-deleted rows are invisible to
    this lookup, so a re-injection after deletion is treated as brand new.
    """
    row = db.conn.execute(
        """
        SELECT m.id, m.content_hash
          FROM memories m
          JOIN chunks_meta cm ON cm.memory_id = m.id
         WHERE cm.source_file = ?
           AND cm.chunk_index = ?
           AND m.deleted_at IS NULL
         LIMIT 1
        """,
        (source_file, chunk_index),
    ).fetchone()
    if row is None:
        return None
    return ExistingChunk(memory_id=row["id"], content_hash=row["content_hash"])


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
    print(f"  Batch size: {BATCH_SIZE}")
    print(f"  Ollama:    {OLLAMA_URL} / {OLLAMA_MODEL}")

    db = Database(DB_PATH)
    ec = OllamaEmbeddingClient(base_url=OLLAMA_URL, model=OLLAMA_MODEL)

    files = scan_markdown_files(MEMORY_DIR)
    print(f"  Files:      {len(files)}")

    total = 0
    skipped = 0
    updated = 0

    # Batch queue — collect chunk texts + metadata, embed in groups of BATCH_SIZE.
    class _Queued:
        source_file: str
        chunk_content: str
        chunk_hash: str
        chunk_index: int

    batch: list[_Queued] = []

    def _flush_batch() -> None:
        nonlocal total, skipped
        if not batch:
            return
        try:
            vecs = ec.embed_batch([q.chunk_content for q in batch])
        except EmbeddingError as exc:
            print(f"  [fail] batch of {len(batch)}: embedding error ({exc})")
            skipped += len(batch)
            batch.clear()
        if total > 0 and total % 100 == 0:
            print(f"  {total} chunks...")
            return

        for q, vec in zip(batch, vecs):
            try:
                store_memory_atomic(
                    db,
                    namespace="default",
                    content=q.chunk_content,
                    content_hash=q.chunk_hash,
                    chunks=[
                        ChunkInput(
                            content=q.chunk_content,
                            embedding=json.dumps(vec, separators=(",", ":")).encode("utf-8"),
                            chunk_index=q.chunk_index,
                        )
                    ],
                    source_file=q.source_file,
                )
                total += 1
            except Exception as exc:
                print(f"  [fail] {q.source_file} chunk {q.chunk_index}: store error ({exc})")
                skipped += 1
        batch.clear()
        if total > 0 and total % 100 == 0:
            print(f"  {total} chunks...")

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

            # ── Incremental update: content-hash comparison ──
            chunk_hash = hashlib.sha256(chunk_content.encode("utf-8")).hexdigest()
            existing = _lookup_existing(db, source_file, ci)

            if existing is not None:
                if existing.content_hash == chunk_hash:
                    # Unchanged — skip.
                    skipped += 1
                    continue
                else:
                    # Content has changed — soft-delete old version, insert new.
                    db.soft_delete_memory(existing.memory_id)
                    updated += 1
                    # Fall through to insertion below.

            # ── Queue for batch embedding ──
            batch.append(_Queued())
            batch[-1].source_file = source_file
            batch[-1].chunk_content = chunk_content
            batch[-1].chunk_hash = chunk_hash
            batch[-1].chunk_index = ci

            if len(batch) >= BATCH_SIZE:
                _flush_batch()

    # Flush remaining chunks.
    _flush_batch()

    print(f"  Total:   {total} chunks injected")
    print(f"  Updated: {updated} chunks (content changed, old version softly deleted)")
    print(f"  Skipped: {skipped} chunks (unchanged or errored)")
    counts = db.row_counts()
    print(f"  DB now:  {counts['memories']} memories, {counts['chunks_meta']} meta, "
          f"{counts['chunks_vec']} vec")

    # ── Dedup similarity scan ──────────────────────────────────────────
    # Compare each newly-injected chunk against the existing vector pool.
    # Chunks whose nearest-neighbour similarity crosses the dedup threshold
    # are flagged pending_review for LLM adjudication.
    if total > 0:
        print(f"\n  Scanning {total} new chunks for dedup candidates...")
        from memory_mcp.dedup import DEFAULT_DEDUP_THRESHOLD
        flagged = 0
        with db.transaction() as conn:
            # Collect rowids of recently injected chunks.
            new_rows = conn.execute(
                "SELECT rowid, content, memory_id FROM chunks_meta "
                "WHERE pending_review = 0 ORDER BY rowid DESC LIMIT ?",
                (total * 2,),  # generous window
            ).fetchall()

            if new_rows:
                for nr in new_rows:
                    # Embed chunk content for similarity search.
                    try:
                        vec = ec.embed(nr["content"])
                        qj = json.dumps(vec, separators=(",", ":"))
                    except EmbeddingError:
                        continue

                    # Find nearest neighbour (excluding self).
                    neighbours = conn.execute(
                        "SELECT rowid, distance FROM chunks_vec "
                        "WHERE embedding MATCH ? AND rowid != ? "
                        "ORDER BY distance LIMIT 1",
                        (qj, nr["rowid"]),
                    ).fetchall()

                    if neighbours and (1.0 - neighbours[0]["distance"]) >= DEFAULT_DEDUP_THRESHOLD:
                        conn.execute(
                            "UPDATE chunks_meta SET pending_review = 1 WHERE rowid = ?",
                            (nr["rowid"],),
                        )
                        flagged += 1

        if flagged > 0:
            print(f"  Pending review: {flagged} chunks flagged for LLM adjudication")
            print(f"  → LLM agent: call get_pending_reviews() to review, "
                  f"then resolve_dedup_review() to commit")
        else:
            print(f"  Pending review: 0 (no near-duplicates found)")

    db.close()


if __name__ == "__main__":
    main()
