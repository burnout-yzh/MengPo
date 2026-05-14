from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import json
from memory_mcp import ChunkInput, Database, store_memory_atomic
import json
from memory_mcp.consistency import run_consistency_check


def _vec(seed: int = 0, dim: int = 1024) -> bytes:
    """Generate dummy embedding vector for vec0."""
    v = [float(seed % 256) / 256.0] * dim
    import json; return json.dumps(v, separators=(",", ":")).encode()

def _chunk(i: int) -> ChunkInput:
    return ChunkInput(content=f"c{i}", embedding=_vec(0), chunk_index=i)


class ConsistencyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Database(Path(self.tmp.name) / "consistency.db")

    def tearDown(self) -> None:
        self.db.close()
        self.tmp.cleanup()

    def test_report_ok_for_normal_atomic_writes(self) -> None:
        _ = store_memory_atomic(
            self.db,
            namespace="demo",
            content="hello",
            content_hash="h1",
            chunks=[_chunk(0), _chunk(1)],
        )

        report = run_consistency_check(self.db)
        self.assertTrue(report.ok)
        self.assertEqual(report.critical_issues, 0)
        self.assertEqual(report.duplicate_chunk_index_count, 0)

    def test_report_flags_orphan_memory_without_chunks(self) -> None:
        _ = self.db.conn.execute(
            """
            INSERT INTO memories (namespace, content, content_hash)
            VALUES (?, ?, ?)
            """,
            ("demo", "orphan", "h-orphan"),
        )

        report = run_consistency_check(self.db)
        self.assertFalse(report.ok)
        self.assertEqual(report.orphan_memories_count, 1)

    def test_report_flags_duplicate_chunk_index_within_memory(self) -> None:
        _ = store_memory_atomic(
            self.db,
            namespace="demo",
            content="hello",
            content_hash="h1",
            chunks=[_chunk(0), _chunk(1)],
        )
        rows = self.db.conn.execute(
            "SELECT rowid FROM chunks_meta ORDER BY rowid"
        ).fetchall()
        self.db.conn.execute(
            "UPDATE chunks_meta SET chunk_index = ? WHERE rowid = ?",
            (0, rows[1][0]),
        )

        report = run_consistency_check(self.db)
        self.assertFalse(report.ok)
        self.assertEqual(report.duplicate_chunk_index_count, 1)


class DatabaseTransactionTests(unittest.TestCase):
    def test_transaction_rolls_back_on_exception(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            db = Database(Path(td) / "rollback.db")
            try:
                with self.assertRaises(RuntimeError):
                    with db.transaction() as conn:
                        conn.execute(
                            "INSERT INTO memories (namespace, content, content_hash) VALUES (?, ?, ?)",
                            ("demo", "temp", "h-temp"),
                        )
                        raise RuntimeError("force rollback")

                rows = db.list_memories(namespace="demo", include_deleted=True)
                self.assertEqual(rows, [])
            finally:
                db.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
