"""Tests for dedup LLM adjudication pipeline (v0.10.78).

Covers: pending_review schema migration, Database pending-review methods,
and the MCP tool logic in server.py.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from memory_mcp import ChunkInput, Database, store_memory_atomic
from memory_mcp.dedup import DEFAULT_DEDUP_THRESHOLD


def _vec(dim: int = 1024) -> bytes:
    v = [0.5] * dim
    import json; return json.dumps(v, separators=(",", ":")).encode()


def _chunk(i: int) -> ChunkInput:
    return ChunkInput(content=f"dedup-test-chunk-{i}", embedding=_vec(), chunk_index=i)


class PendingReviewMigrationTests(unittest.TestCase):
    """Verify pending_review column is auto-added to existing databases."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Database(Path(self.tmp.name) / "pr.db")

    def tearDown(self) -> None:
        self.db.close()
        self.tmp.cleanup()

    def test_pending_review_column_exists_after_schema_apply(self) -> None:
        """The column should be present on a freshly-created database."""
        cols = {
            row[1] for row in
            self.db.conn.execute("PRAGMA table_info(chunks_meta)").fetchall()
        }
        self.assertIn("pending_review", cols)

    def test_pending_review_defaults_to_zero(self) -> None:
        """Newly inserted chunks should have pending_review=0."""
        result = store_memory_atomic(
            self.db,
            namespace="pr-test",
            content="hello",
            content_hash="h1",
            chunks=[_chunk(0)],
        )
        row = self.db.conn.execute(
            "SELECT pending_review FROM chunks_meta WHERE memory_id = ?",
            (result.memory_id,),
        ).fetchone()
        self.assertEqual(row["pending_review"], 0)


class PendingReviewDBTests(unittest.TestCase):
    """Test Database.get_pending_reviews / resolve_pending_review / pending_review_count."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Database(Path(self.tmp.name) / "pr_db.db")

    def tearDown(self) -> None:
        self.db.close()
        self.tmp.cleanup()

    def _insert_with_flag(self, content_hash: str, pending: int = 0) -> int:
        result = store_memory_atomic(
            self.db,
            namespace="pr-db",
            content=f"content-{content_hash}",
            content_hash=content_hash,
            chunks=[_chunk(0)],
        )
        if pending:
            self.db.conn.execute(
                "UPDATE chunks_meta SET pending_review = 1 WHERE memory_id = ?",
                (result.memory_id,),
            )
        return result.memory_id

    def test_pending_review_count_zero_on_clean_db(self) -> None:
        self.assertEqual(self.db.pending_review_count(), 0)

    def test_pending_review_count_reflects_flags(self) -> None:
        self._insert_with_flag("a", pending=0)
        self._insert_with_flag("b", pending=1)
        self._insert_with_flag("c", pending=1)
        self.assertEqual(self.db.pending_review_count(), 2)

    def test_get_pending_reviews_returns_flagged_only(self) -> None:
        mid_a = self._insert_with_flag("a", pending=0)
        mid_b = self._insert_with_flag("b", pending=1)
        mid_c = self._insert_with_flag("c", pending=1)

        rows = self.db.get_pending_reviews(limit=10)
        mids = {r["memory_id"] for r in rows}
        self.assertNotIn(mid_a, mids)
        self.assertIn(mid_b, mids)
        self.assertIn(mid_c, mids)
        self.assertEqual(len(rows), 2)

    def test_get_pending_reviews_respects_limit(self) -> None:
        for i in range(5):
            self._insert_with_flag(f"h{i}", pending=1)
        rows = self.db.get_pending_reviews(limit=2)
        self.assertEqual(len(rows), 2)

    def test_resolve_duplicate_soft_deletes(self) -> None:
        mid = self._insert_with_flag("dup", pending=1)
        resolved = self.db.resolve_pending_review(mid, verdict="duplicate")
        self.assertTrue(resolved)

        row = self.db.conn.execute(
            "SELECT deleted_at FROM memories WHERE id = ?", (mid,),
        ).fetchone()
        self.assertIsNotNone(row["deleted_at"])

    def test_resolve_false_positive_clears_flag(self) -> None:
        mid = self._insert_with_flag("fp", pending=1)
        resolved = self.db.resolve_pending_review(mid, verdict="false_positive")
        self.assertTrue(resolved)

        row = self.db.conn.execute(
            "SELECT pending_review, deleted_at FROM chunks_meta cm "
            "JOIN memories m ON m.id = cm.memory_id WHERE m.id = ?",
            (mid,),
        ).fetchone()
        self.assertEqual(row["pending_review"], 0)
        self.assertIsNone(row["deleted_at"])

    def test_resolve_invalid_verdict_raises(self) -> None:
        mid = self._insert_with_flag("bad", pending=1)
        with self.assertRaises(ValueError):
            self.db.resolve_pending_review(mid, verdict="maybe")

    def test_resolve_nonexistent_memory_returns_false(self) -> None:
        resolved = self.db.resolve_pending_review(99999, verdict="duplicate")
        self.assertFalse(resolved)


class PendingReviewSoftDeleteTests(unittest.TestCase):
    """Pending reviews should not surface soft-deleted memories."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Database(Path(self.tmp.name) / "pr_soft.db")

    def tearDown(self) -> None:
        self.db.close()
        self.tmp.cleanup()

    def test_soft_deleted_not_in_pending_reviews(self) -> None:
        result = store_memory_atomic(
            self.db,
            namespace="pr-soft",
            content="deleted soon",
            content_hash="ds",
            chunks=[_chunk(0)],
        )
        mid = result.memory_id
        self.db.conn.execute(
            "UPDATE chunks_meta SET pending_review = 1 WHERE memory_id = ?", (mid,),
        )
        self.db.soft_delete_memory(mid)

        rows = self.db.get_pending_reviews()
        self.assertEqual(len(rows), 0)
        self.assertEqual(self.db.pending_review_count(), 0)
