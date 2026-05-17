"""SQLite connection factory with manual transaction control.

We disable the default Python DB-API implicit transaction behaviour
(`isolation_level=None`) so the atomic-store layer can issue explicit
`BEGIN IMMEDIATE` / `COMMIT` / `ROLLBACK` and own the transaction boundary.

Foreign keys are enabled so that an inconsistent (memory/meta/vec) state
is impossible at rest — any attempt to leave an orphan row fails the
transaction before commit.
"""

from __future__ import annotations

import sqlite3
import sqlite_vec
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
UTC = timezone.utc
from pathlib import Path
from typing import Any, Iterator

from .schema import apply_schema


def connect(path: str | Path = ":memory:") -> sqlite3.Connection:
    """Open a SQLite connection configured for manual transactions.

    Parameters
    ----------
    path:
        Filesystem path, or ``":memory:"`` for ephemeral test databases.
    """
    conn = sqlite3.connect(
        str(path),
        isolation_level=None,  # manual transaction control
        detect_types=sqlite3.PARSE_DECLTYPES,
    )
    conn.row_factory = sqlite3.Row
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    # Enforce referential integrity so orphaned chunks cannot exist at rest.
    conn.execute("PRAGMA foreign_keys = ON;")
    # Durable crash-safety for the atomic-write contract.
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    apply_schema(conn)
    return conn


class Database:
    """Thin wrapper exposing a single-transaction context manager."""

    def __init__(self, path: str | Path = ":memory:"):
        self.path = str(path)
        self.conn = connect(self.path)
        self._tx_lock = threading.RLock()

    def close(self) -> None:
        try:
            self.conn.close()
        except sqlite3.ProgrammingError:
            pass

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """Run a block inside a single ``BEGIN IMMEDIATE`` / ``COMMIT`` pair.

        On any exception, a ``ROLLBACK`` is issued and the exception is
        re-raised. This is the *only* write boundary callers should use —
        no partial commits are permitted inside.
        """
        with self._tx_lock:
            self.conn.execute("BEGIN IMMEDIATE;")
            try:
                yield self.conn
            except BaseException:
                # BaseException: catch KeyboardInterrupt too, so we never leak
                # a half-open transaction.
                try:
                    self.conn.execute("ROLLBACK;")
                except sqlite3.Error:
                    # Already rolled back by the engine (e.g. deferred FK failure).
                    pass
                raise
            else:
                self.conn.execute("COMMIT;")

    # Convenience for tests / ops.
    def row_counts(self) -> dict[str, int]:
        cur = self.conn.cursor()
        try:
            return {
                "memories":    cur.execute("SELECT COUNT(*) FROM memories").fetchone()[0],
                "chunks_meta": cur.execute("SELECT COUNT(*) FROM chunks_meta").fetchone()[0],
                "chunks_vec":  cur.execute("SELECT COUNT(*) FROM chunks_vec").fetchone()[0],
            }
        finally:
            cur.close()

    def soft_delete_memory(self, memory_id: int) -> bool:
        """Soft-delete one memory by setting ``deleted_at`` timestamp.

        Returns ``True`` when a visible row was deleted, ``False`` when the
        memory does not exist or is already soft-deleted.
        """
        deleted_at = datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")
        with self.transaction() as conn:
            cur = conn.execute(
                """
                UPDATE memories
                   SET deleted_at = ?,
                       updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now')
                 WHERE id = ?
                   AND deleted_at IS NULL
                """,
                (deleted_at, memory_id),
            )
            return cur.rowcount > 0

    def list_memories(
        self,
        *,
        namespace: str,
        limit: int = 50,
        offset: int = 0,
        include_deleted: bool = False,
    ) -> list[dict[str, Any]]:
        """List memories in one namespace.

        Default behaviour hides soft-deleted rows. Set ``include_deleted=True``
        to emulate recycle-bin listing.
        """
        where_deleted = "" if include_deleted else "AND deleted_at IS NULL"
        rows = self.conn.execute(
            f"""
            SELECT id, namespace, content, source_file, content_hash,
                   metadata_json, deleted_at,
                   last_effective_recall_at, effective_recall_count,
                   created_at, updated_at
              FROM memories
             WHERE namespace = ?
               {where_deleted}
             ORDER BY id DESC
             LIMIT ? OFFSET ?
            """,
            (namespace, limit, offset),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_pending_reviews(self, *, limit: int = 20) -> list[dict[str, Any]]:
        """Return chunks flagged as pending dedup adjudication.

        Each row provides enough context for an LLM to judge whether the
        chunk is a true duplicate or a false positive.
        """
        rows = self.conn.execute(
            """
            SELECT m.id AS memory_id, m.content AS memory_content,
                   cm.rowid AS chunk_rowid, cm.content AS chunk_content,
                   cm.source_file, cm.chunk_index,
                   m.created_at
              FROM chunks_meta cm
              JOIN memories m ON m.id = cm.memory_id
             WHERE cm.pending_review = 1
               AND m.deleted_at IS NULL
             ORDER BY m.created_at DESC
             LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]

    def resolve_pending_review(
        self, memory_id: int, *, verdict: str
    ) -> bool:
        """Resolve one pending dedup review.

        *verdict* must be ``"duplicate"`` (soft-delete the memory and its
        chunks) or ``"false_positive"`` (clear the pending flag, keep the
        memory).  Returns True when a row was affected.
        """
        if verdict not in ("duplicate", "false_positive"):
            raise ValueError("verdict must be 'duplicate' or 'false_positive'")

        if verdict == "duplicate":
            return self.soft_delete_memory(memory_id)
        else:
            with self.transaction() as conn:
                cur = conn.execute(
                    "UPDATE chunks_meta SET pending_review = 0 WHERE memory_id = ?",
                    (memory_id,),
                )
                return cur.rowcount > 0

    def pending_review_count(self) -> int:
        """Return the number of chunks awaiting adjudication."""
        row = self.conn.execute(
            """
            SELECT COUNT(*)
              FROM chunks_meta cm
              JOIN memories m ON m.id = cm.memory_id
             WHERE cm.pending_review = 1 AND m.deleted_at IS NULL
            """
        ).fetchone()
        return row[0] if row else 0

    def Sansheng_Stone(  # 真名: write_back_effective_recalls() — S3 time-position boost
        self,
        *,
        memory_ids: list[int],
        shrink_factor: float = 0.368,  # 1/e -- natural decay constant
        now: datetime | None = None,
    ) -> int:
        """Sansheng_Stone (三生石): Apply S3 write-back to effective memories only.

        We persist a reinforced virtual recall timestamp by shrinking the
        elapsed interval from prior effective recall to `now`.

        With shrink_factor=1/e (0.368), the anchor is shrunk to 36.8%
        of the elapsed interval -- pulled 63.2% toward now, mimicking
        biological memory reconsolidation. After 10 days of decay,
        memory behaves as if only ~3.68 days have passed.

            reinforced_at = now - (now - previous_effective_at) * shrink_factor

        Returns number of rows updated. Empty input is a no-op.
        """
        if not memory_ids:
            return 0
        if shrink_factor <= 0:
            raise ValueError("shrink_factor must be > 0")

        now_utc = now.astimezone(UTC) if now is not None else datetime.now(UTC)
        placeholders = ",".join("?" for _ in memory_ids)
        with self.transaction() as conn:
            rows = conn.execute(
                f"""
                SELECT id, last_effective_recall_at, created_at
                  FROM memories
                 WHERE id IN ({placeholders})
                   AND deleted_at IS NULL
                """,
                tuple(memory_ids),
            ).fetchall()

            updated = 0
            for row in rows:
                base_time = _parse_utc_iso(str(row["last_effective_recall_at"])) if row["last_effective_recall_at"] else _parse_utc_iso(str(row["created_at"]))
                delta = now_utc - base_time
                if delta.total_seconds() < 0:
                    delta = now_utc - now_utc
                reinforced_at = now_utc - (delta * shrink_factor)  # anchor shrunk to 36.8% (1/e) of elapsed interval
                reinforced_iso = _to_iso_z(reinforced_at)
                cur = conn.execute(
                    """
                    UPDATE memories
                       SET last_effective_recall_at = ?,
                           effective_recall_count = effective_recall_count + 1,
                           updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now')
                     WHERE id = ?
                    """,
                    (reinforced_iso, row["id"]),
                )
                updated += cur.rowcount

            return updated


def _parse_utc_iso(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed.astimezone(UTC)


def _to_iso_z(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")
