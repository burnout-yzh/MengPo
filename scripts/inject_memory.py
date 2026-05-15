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
import struct
import os
import sys
import time
from dataclasses import dataclass
from datetime import datetime
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
CHUNK_MIN_SIZE = int(os.getenv("MENGPO_CHUNK_MIN_SIZE", "160"))
CHUNK_SIZE = int(os.getenv("MENGPO_CHUNK_SIZE", "500"))
BATCH_SIZE = int(os.getenv("MENGPO_BATCH_SIZE", "15"))
OLLAMA_URL = os.getenv("MENGPO_OLLAMA_URL", "http://127.0.0.1:11434")
OLLAMA_MODEL = os.getenv("MENGPO_OLLAMA_MODEL", "qwen3-embedding-0.6b")


# ── Chunking ───────────────────────────────────────────────────────────────

def chunk_text(text: str, max_size: int = CHUNK_SIZE, min_size: int = CHUNK_MIN_SIZE) -> list[str]:
    """Split text into semantic chunks for embedding.

    Strategy:
    1. Split on double-newline (paragraph boundaries).
    2. Short paragraphs accumulate in a buffer until *min_size* is reached.
    3. Hard boundaries (heading, hr, code fence) flush the buffer.
    4. Long paragraphs are split at sentence boundaries near *max_size*.
    """
    _HARD_BOUNDARY = {"---", "***", "___"}  # horizontal-rule variants
    _CODE_FENCE = "```"

    raw_paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    if len(raw_paragraphs) <= 1:
        # Single-paragraph edge case — split by sentence
        return _split_long_paragraph(raw_paragraphs[0] if raw_paragraphs else "", max_size)

    result: list[str] = []
    buffer: str = ""

    def _emit(chunk: str) -> None:
        nonlocal buffer
        if not chunk.strip():
            return
        # If buffer has content and chunk can be merged without exceeding max
        if buffer and len(buffer) + len(chunk) + 2 <= max_size * 1.2:
            buffer += "\n\n" + chunk
        else:
            if buffer:
                result.append(buffer)
            buffer = chunk
        # Emit when buffer reaches min_size
        if len(buffer) >= min_size:
            result.append(buffer)
            buffer = ""

    for para in raw_paragraphs:
        # Detect hard boundaries
        stripped = para.strip()
        if stripped in _HARD_BOUNDARY:
            if buffer:
                result.append(buffer)
                buffer = ""
            continue  # skip horizontal rules entirely
        if stripped.startswith(_CODE_FENCE):
            if buffer:
                result.append(buffer)
                buffer = ""
            result.append(para)  # code fence as standalone chunk
            continue

        # Long paragraph — split at sentence boundaries
        if len(para) > max_size:
            if buffer:
                result.append(buffer)
                buffer = ""
            sub_chunks = _split_long_paragraph(para, max_size)
            for sc in sub_chunks:
                _emit(sc)
            continue

        # Short/medium paragraph — accumulate
        _emit(para)

    # Flush remaining buffer
    if buffer:
        result.append(buffer)

    return result


def _split_long_paragraph(text: str, max_size: int) -> list[str]:
    """Split a long paragraph at sentence boundaries near max_size."""
    if len(text) <= max_size:
        return [text] if text.strip() else []

    # Sentence delimiters (Chinese + English)
    _DELIM = ".!?;！？；。\n"
    chunks: list[str] = []
    pos = 0

    while pos < len(text):
        end = min(pos + max_size, len(text))
        if end == len(text):
            chunks.append(text[pos:].strip())
            break

        # Search backward from end for nearest sentence boundary
        window_start = max(pos, end - 80)
        best = -1
        for i in range(end, window_start - 1, -1):
            if text[i] in _DELIM:
                best = i + 1  # include the delimiter
                break

        if best > pos:
            chunks.append(text[pos:best].strip())
            pos = best
        else:
            # No sentence boundary found — hard cut
            chunks.append(text[pos:end].strip())
            pos = end

    # Merge trailing short chunks into the previous one
    if len(chunks) >= 2 and len(chunks[-1]) < 30:
        chunks[-2] = chunks[-2] + "\n" + chunks[-1]
        chunks.pop()

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


def _vec_blob_to_json(blob: bytes) -> str | None:
    """Convert sqlite-vec vec0 embedding BLOB to JSON float array.

    vec0 BLOB format: <4 bytes: dim as uint32 LE><dim * 4 bytes: float32 LE>
    """
    if blob is None or len(blob) < 4:
        return None
    dim = struct.unpack_from("<I", blob)[0]
    if len(blob) < 4 + dim * 4:
        return None
    floats = struct.unpack_from(f"<{dim}f", blob, 4)
    return json.dumps(list(floats), separators=(",", ":"))


# ── File scanner ───────────────────────────────────────────────────────────

def scan_markdown_files(root: str | Path) -> list[Path]:
    """Recursively collect ``*.md`` files under *root*."""
    root_path = Path(root).expanduser().resolve()
    if not root_path.is_dir():
        raise FileNotFoundError(f"Memory directory not found: {root_path}")
    return sorted(root_path.rglob("*.md"))


# ── Main ───────────────────────────────────────────────────────────────────

def main() -> None:
    t0 = time.time()
    log_lines: list[str] = []

    def _log(msg: str) -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        line = f"[{ts}] {msg}"
        print(line)
        log_lines.append(line)

    _log("=== MengPo Memory Injection ===")
    _log(f"  DB:        {DB_PATH}")
    _log(f"  Memory dir: {MEMORY_DIR}")
    _log(f"  Chunk size: {CHUNK_MIN_SIZE}-{CHUNK_SIZE} chars")
    _log(f"  Batch size: {BATCH_SIZE}")
    _log(f"  Ollama:    {OLLAMA_URL} / {OLLAMA_MODEL}")

    db = Database(DB_PATH)
    ec = OllamaEmbeddingClient(base_url=OLLAMA_URL, model=OLLAMA_MODEL)

    files = scan_markdown_files(MEMORY_DIR)
    _log(f"  Files:      {len(files)}")

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
            _log(f"  [fail] batch of {len(batch)}: embedding error ({exc})")
            skipped += len(batch)
            batch.clear()
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
                _log(f"  [fail] {q.source_file} chunk {q.chunk_index}: store error ({exc})")
                skipped += 1
        batch.clear()
        if total > 0 and total % 50 == 0:
            _log(f"  {total} chunks ({time.time()-t0:.0f}s)")

    for fp in files:
        # Derive a relative path for stable source_file dedup.
        try:
            source_file = str(fp.relative_to(Path(MEMORY_DIR).resolve()))
        except ValueError:
            source_file = fp.name

        try:
            content = fp.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            _log(f"  [skip] {source_file}: read error ({exc})")
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

    _log(f"  Total:   {total} chunks injected")
    _log(f"  Updated: {updated} chunks (content changed, old version softly deleted)")
    _log(f"  Skipped: {skipped} chunks (unchanged or errored)")
    counts = db.row_counts()
    _log(f"  DB now:  {counts['memories']} memories, {counts['chunks_meta']} meta, {counts['chunks_vec']} vec")

    # ── Dedup similarity scan ──────────────────────────────────────────
    # Reuse vectors already in chunks_vec (written during injection).
    # No Ollama re-embedding — pure SQL JOIN + vec0 MATCH.
    if total > 0:
        _log(f"  Dedup scan: {total} candidates")
        t_dedup = time.time()
        from memory_mcp.dedup import DEFAULT_DEDUP_THRESHOLD

        with db.transaction() as conn:
            new_rows = conn.execute(
                "SELECT m.rowid, c.embedding "
                "FROM chunks_meta m "
                "JOIN chunks_vec c ON m.rowid = c.rowid "
                "WHERE m.pending_review = 0 "
                "ORDER BY m.rowid DESC LIMIT ?",
                (total * 2,),
            ).fetchall()

        flagged = 0
        with db.transaction() as conn:
            for nr in new_rows:
                emb_json = _vec_blob_to_json(nr["embedding"])
                if emb_json is None:
                    continue

                neighbours = conn.execute(
                    "SELECT rowid, distance FROM chunks_vec "
                    "WHERE embedding MATCH ? AND rowid != ? "
                    "ORDER BY distance LIMIT 1",
                    (emb_json, nr["rowid"]),
                ).fetchall()

                if neighbours and (1.0 - neighbours[0]["distance"]) >= DEFAULT_DEDUP_THRESHOLD:
                    conn.execute(
                        "UPDATE chunks_meta SET pending_review = 1 WHERE rowid = ?",
                        (nr["rowid"],),
                    )
                    flagged += 1

        if flagged > 0:
            _log(f"  Pending review: {flagged} flagged ({time.time()-t_dedup:.0f}s)")
            _log(f"  → call get_pending_reviews() then resolve_dedup_review()")
        else:
            _log(f"  Pending review: 0 ({time.time()-t_dedup:.0f}s)")

    # ── Release GPU ──
    try:
        import subprocess as _sp
        _sp.run(["ollama", "stop", OLLAMA_MODEL], capture_output=True, timeout=30)
        _log(f"  GPU released (ollama stop {OLLAMA_MODEL})")
    except Exception:
        _log(f"  GPU release skipped — run 'ollama stop {OLLAMA_MODEL}' manually if needed")

    elapsed = time.time() - t0
    _log(f"  Total time: {elapsed:.1f}s")
    _log("=== Injection complete ===")

    # Write log to file
    log_path = Path(DB_PATH).parent / "inject.log"
    try:
        with open(log_path, "w", encoding="utf-8") as f:
            f.write("\n".join(log_lines) + "\n")
    except OSError:
        pass

    db.close()


if __name__ == "__main__":
    main()
