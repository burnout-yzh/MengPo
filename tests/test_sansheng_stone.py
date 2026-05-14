"""S3 write-back tests for Sansheng_Stone (三生石).

Run with: ``python -m unittest tests.test_sansheng_stone -v``
"""

from __future__ import annotations

import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

import json
from memory_mcp import ChunkInput, Database, store_memory_atomic


def _vec(dim: int = 1024) -> bytes:
    v = [0.5] * dim
    import json; return json.dumps(v, separators=(",", ":")).encode()


def _chunk(i: int) -> ChunkInput:
    return ChunkInput(content=f"c{i}", embedding=_vec(), chunk_index=i)


class SanshengStoneTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Database(Path(self.tmp.name) / "s3.db")
        self.now = datetime(2026, 5, 14, 12, 0, 0, tzinfo=UTC)

    def tearDown(self) -> None:
        self.db.close()
        self.tmp.cleanup()

    # ── helpers ──

    def _create_memory(self) -> int:
        """Insert one chunk and return the memory_id."""
        result = store_memory_atomic(
            self.db,
            namespace="s3-test",
            content="alpha bravo charlie",
            content_hash="abc",
            chunks=[_chunk(0)],
        )
        return result.memory_id

    def _assert_effective_state(self, memory_id: int, *, expected_count: int, non_null: bool) -> None:
        row = self.db.conn.execute(
            "SELECT last_effective_recall_at, effective_recall_count "
            "FROM memories WHERE id = ?",
            (memory_id,),
        ).fetchone()
        self.assertIsNotNone(row, f"memory_id={memory_id} not found")
        if non_null:
            self.assertIsNotNone(row["last_effective_recall_at"])
        else:
            self.assertIsNone(row["last_effective_recall_at"])
        self.assertEqual(row["effective_recall_count"], expected_count)

    # ── tests ──

    def test_write_back_updates_anchor_and_counter(self) -> None:
        """S3 main flow: valid memory_id → last_effective_recall_at set, counter bumped."""
        mid = self._create_memory()

        # Before: virgin memory — no recall yet.
        self._assert_effective_state(mid, expected_count=0, non_null=False)

        updated = self.db.Sansheng_Stone(memory_ids=[mid], now=self.now)
        self.assertEqual(updated, 1)

        self._assert_effective_state(mid, expected_count=1, non_null=True)

        # Second write-back bumps counter.
        updated2 = self.db.Sansheng_Stone(memory_ids=[mid], now=self.now)
        self.assertEqual(updated2, 1)
        self._assert_effective_state(mid, expected_count=2, non_null=True)

    def test_nonexistent_memory_ids_are_silently_ignored(self) -> None:
        """S3 edge: invalid / non-existent memory_ids → return 0, no crash."""
        updated = self.db.Sansheng_Stone(memory_ids=[99999], now=self.now)
        self.assertEqual(updated, 0)

        # Mixed: one valid + one invalid.
        mid = self._create_memory()
        updated = self.db.Sansheng_Stone(memory_ids=[mid, 99998], now=self.now)
        self.assertEqual(updated, 1)
        self._assert_effective_state(mid, expected_count=1, non_null=True)

    def test_empty_input_is_noop(self) -> None:
        """S3 edge: empty list → return 0."""
        self.assertEqual(self.db.Sansheng_Stone(memory_ids=[]), 0)

    def test_shrink_factor_0_raises(self) -> None:
        """S3 param: shrink_factor <= 0 → ValueError."""
        mid = self._create_memory()
        with self.assertRaises(ValueError):
            self.db.Sansheng_Stone(memory_ids=[mid], shrink_factor=0.0)
        with self.assertRaises(ValueError):
            self.db.Sansheng_Stone(memory_ids=[mid], shrink_factor=-0.1)

    def test_shrink_factor_anchors_time_correctly(self) -> None:
        """S3 logic: anchored time respects shrink_factor formula.

        Formula: reinforced_at = now - (now - previous_effective_at) * shrink_factor

        On a virgin memory (no prior recall), base_time = created_at.
        """
        mid = self._create_memory()

        # Get the actual created_at from the database.
        row_created = self.db.conn.execute(
            "SELECT created_at FROM memories WHERE id = ?", (mid,),
        ).fetchone()
        created_at = datetime.fromisoformat(
            row_created["created_at"].replace("Z", "+00:00")
        )

        # After write-back, anchored must move from created_at toward now.
        self.db.Sansheng_Stone(memory_ids=[mid], now=self.now, shrink_factor=0.368)
        row = self.db.conn.execute(
            "SELECT last_effective_recall_at FROM memories WHERE id = ?", (mid,),
        ).fetchone()
        anchored = datetime.fromisoformat(row["last_effective_recall_at"].replace("Z", "+00:00"))

        self.assertGreater(anchored, created_at,
                           "Anchored time must be later than created_at")
        self.assertLess(anchored, self.now,
                        "Anchored time must be earlier than now")

        # Verify formula: anchored ≈ now - (now - created_at) * 0.368
        expected = self.now - timedelta(
            seconds=(self.now - created_at).total_seconds() * 0.368
        )
        delta_s = abs((expected - anchored).total_seconds())
        self.assertLess(delta_s, 5.0,
                        f"Formula mismatch: anchored={anchored} expected={expected}")

        # Second write-back after 2 hours: anchor should move further.
        later = self.now + timedelta(hours=2)
        self.db.Sansheng_Stone(memory_ids=[mid], now=later, shrink_factor=0.368)
        row2 = self.db.conn.execute(
            "SELECT last_effective_recall_at FROM memories WHERE id = ?", (mid,),
        ).fetchone()
        anchored2 = datetime.fromisoformat(row2["last_effective_recall_at"].replace("Z", "+00:00"))

        expected2 = later - timedelta(
            seconds=(later - anchored).total_seconds() * 0.368
        )
        delta_s2 = abs((expected2 - anchored2).total_seconds())
        self.assertLess(delta_s2, 5.0,
                        f"Second formula mismatch: anchored2={anchored2} expected2={expected2}")
        self.assertGreater(anchored2, anchored,
                           "Second anchor should be later than first")


class SanshengStoneSoftDeleteTests(unittest.TestCase):
    """Verify that soft-deleted memories do not receive write-backs."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Database(Path(self.tmp.name) / "s3_soft.db")
        self.now = datetime(2026, 5, 14, 12, 0, 0, tzinfo=UTC)

    def tearDown(self) -> None:
        self.db.close()
        self.tmp.cleanup()

    def test_deleted_memory_is_skipped(self) -> None:
        result = store_memory_atomic(
            self.db,
            namespace="s3-soft",
            content="to be deleted",
            content_hash="del",
            chunks=[_chunk(0)],
        )
        mid = result.memory_id

        # Soft-delete it.
        deleted = self.db.soft_delete_memory(mid)
        self.assertTrue(deleted)

        # Write-back should skip it.
        updated = self.db.Sansheng_Stone(memory_ids=[mid], now=self.now)
        self.assertEqual(updated, 0)

        # Verify it's still deleted and no recall was recorded.
        row = self.db.conn.execute(
            "SELECT deleted_at, effective_recall_count FROM memories WHERE id = ?",
            (mid,),
        ).fetchone()
        self.assertIsNotNone(row["deleted_at"])
        self.assertEqual(row["effective_recall_count"], 0)
