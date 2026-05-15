"""Atomic ``store_memory`` write boundary (T1).

Contract
--------
``store_memory_atomic`` performs the three-way write of
``memories`` + ``chunks_vec`` + ``chunks_meta`` inside a single SQLite
``BEGIN IMMEDIATE`` transaction. On any exception raised mid-flight
(including injected faults from the caller, embedding failures, DB errors,
or ``KeyboardInterrupt``), the transaction is rolled back and row counts
for all three tables remain unchanged.

Design choices
~~~~~~~~~~~~~~
* The caller supplies pre-computed embeddings as bytes. Embedding I/O is
  deliberately *outside* this function so the transaction does not hold a
  write lock across a 10-second network call (see embedding policy in
  AGENTS.md: timeout=10s, retry=0, owned by T9).
* Fault injection is a first-class parameter so the error-path proof is
  reproducible in tests. In production callers never pass ``fault``.
* We insert all rows first and only commit at the very end. If any INSERT
  raises, ``Database.transaction`` issues ``ROLLBACK`` and no row survives.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from collections.abc import Iterable, Sequence

from .database import Database


class FaultPoint(str, Enum):
    """Injection hooks used by tests to prove rollback behaviour."""

    BEFORE_MEMORY_INSERT = "before_memory_insert"
    AFTER_MEMORY_INSERT = "after_memory_insert"
    BEFORE_VEC_INSERT = "before_vec_insert"
    AFTER_VEC_INSERT = "after_vec_insert"
    BEFORE_META_INSERT = "before_meta_insert"
    AFTER_META_INSERT = "after_meta_insert"
    BEFORE_COMMIT = "before_commit"


class AtomicStoreError(RuntimeError):
    """Raised when the atomic write fails. Rollback has already occurred."""


@dataclass(frozen=True)
class ChunkInput:
    content: str
    embedding: bytes  # JSON string for vec0
    chunk_index: int
    rowid: int | None = None
    paragraph_start: int | None = None
    paragraph_end: int | None = None


@dataclass(frozen=True)
class StoreResult:
    memory_id: int
    chunk_rowids: tuple[int, ...]


def _require_chunks(chunks: Sequence[ChunkInput]) -> None:
    if not chunks:
        raise AtomicStoreError("store_memory requires at least one chunk")
    seen: set[int] = set()
    for c in chunks:
        if c.chunk_index in seen:
            raise AtomicStoreError(f"duplicate chunk_index={c.chunk_index}")
        seen.add(c.chunk_index)
        if len(c.embedding) == 0:
            raise AtomicStoreError("chunk.embedding must not be empty")


def _trip(fault: FaultPoint | None, at: FaultPoint) -> None:
    if fault is at:
        raise AtomicStoreError(f"injected fault at {at.value}")


def store_memory_atomic(
    db: Database,
    *,
    namespace: str,
    content: str,
    content_hash: str,
    chunks: Sequence[ChunkInput],
    source_file: str | None = None,
    metadata: dict[str, object] | None = None,
    created_at: str | None = None,
    fault: FaultPoint | None = None,
) -> StoreResult:
    """Atomically persist one memory + its chunks + their vectors.

    Returns the assigned ``memory_id`` and the list of chunk rowids.
    Raises ``AtomicStoreError`` on any failure; the database is guaranteed
    to be unchanged relative to the pre-call state in that case.
    """
    _require_chunks(chunks)
    metadata_json = json.dumps(metadata, ensure_ascii=False) if metadata else None

    chunk_rowids: list[int] = []
    with db.transaction() as conn:
        cur = conn.cursor()
        try:
            _trip(fault, FaultPoint.BEFORE_MEMORY_INSERT)
            if created_at:
                _ = cur.execute(
                    """
                    INSERT INTO memories (namespace, content, source_file,
                                          content_hash, metadata_json, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (namespace, content, source_file, content_hash, metadata_json, created_at),
                )
            else:
                _ = cur.execute(
                    """
                    INSERT INTO memories (namespace, content, source_file,
                                          content_hash, metadata_json)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (namespace, content, source_file, content_hash, metadata_json),
                )
            if cur.lastrowid is None:
                raise AtomicStoreError("memory insert did not return a rowid")
            memory_id = cur.lastrowid
            _trip(fault, FaultPoint.AFTER_MEMORY_INSERT)

            for chunk in chunks:
                _trip(fault, FaultPoint.BEFORE_VEC_INSERT)
                _ = cur.execute(
                    "INSERT INTO chunks_vec (embedding) VALUES (?)",
                    (chunk.embedding.decode("utf-8") if isinstance(chunk.embedding, bytes) else chunk.embedding,)  # JSON string for vec0,
                )
                rowid = cur.lastrowid
                _trip(fault, FaultPoint.AFTER_VEC_INSERT)

                _trip(fault, FaultPoint.BEFORE_META_INSERT)
                _ = cur.execute(
                    """
                    INSERT INTO chunks_meta (rowid, memory_id, namespace,
                                             chunk_index, content,
                                             source_file,
                                             paragraph_start, paragraph_end)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        rowid,
                        memory_id,
                        namespace,
                        chunk.chunk_index,
                        chunk.content,
                        source_file,
                        chunk.paragraph_start,
                        chunk.paragraph_end,
                    ),
                )
                _trip(fault, FaultPoint.AFTER_META_INSERT)
                chunk_rowids.append(rowid)

            _trip(fault, FaultPoint.BEFORE_COMMIT)
        except AtomicStoreError:
            raise
        except Exception as exc:
            raise AtomicStoreError(str(exc)) from exc
        finally:
            cur.close()

    return StoreResult(memory_id=memory_id, chunk_rowids=tuple(chunk_rowids))


def iter_fault_points() -> Iterable[FaultPoint]:
    """Helper for exhaustive fault-injection tests."""
    return tuple(FaultPoint)
