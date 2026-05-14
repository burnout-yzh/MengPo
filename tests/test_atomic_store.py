"""T1 verification: atomic boundary for store_memory.

Run with: ``python -m unittest tests.test_atomic_store -v``
or:       ``python -m tests.run_fault_matrix``
"""

from __future__ import annotations

import os
import sqlite3
import tempfile
import unittest
from pathlib import Path

import json
from memory_mcp import (
    AtomicStoreError,
    ChunkInput,
    Database,
    FaultPoint,
    store_memory_atomic,
)
import json
from memory_mcp.atomic_store import iter_fault_points


def _vec(seed: int = 0, dim: int = 1024) -> bytes:
    """Generate dummy embedding vector for vec0."""
    v = [float(seed % 256) / 256.0] * dim
    import json; return json.dumps(v, separators=(",", ":")).encode()

def _chunk(i: int, text: str = "hello", dim: int = 1024) -> ChunkInput:
    return ChunkInput(
        content=text,
        embedding=_vec(0),
        chunk_index=i,
        paragraph_start=i,
        paragraph_end=i + 1,
    )


class HappyPathTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Database(Path(self.tmp.name) / "t1.db")

    def tearDown(self) -> None:
        self.db.close()
        self.tmp.cleanup()

    def test_single_chunk_commits_all_three_tables(self) -> None:
        result = store_memory_atomic(
            self.db,
            namespace="projects/demo",
            content="single chunk doc",
            content_hash="h-1",
            chunks=[_chunk(0, "only chunk")],
            source_file="a.md",
            metadata={"tag": "unit"},
        )

        self.assertIsInstance(result.memory_id, int)
        self.assertEqual(len(result.chunk_rowids), 1)
        counts = self.db.row_counts()
        self.assertEqual(counts, {"memories": 1, "chunks_meta": 1, "chunks_vec": 1})

        row = self.db.conn.execute(
            "SELECT namespace, content, source_file, content_hash, metadata_json "
            "FROM memories WHERE id = ?",
            (result.memory_id,),
        ).fetchone()
        self.assertEqual(row["namespace"], "projects/demo")
        self.assertEqual(row["content"], "single chunk doc")
        self.assertEqual(row["source_file"], "a.md")
        self.assertEqual(row["content_hash"], "h-1")
        self.assertIn("unit", row["metadata_json"])

        meta = self.db.conn.execute(
            "SELECT memory_id, namespace, chunk_index FROM chunks_meta"
        ).fetchone()
        self.assertEqual(meta["memory_id"], result.memory_id)
        self.assertEqual(meta["chunk_index"], 0)

        vec_rowid = self.db.conn.execute(
            "SELECT rowid FROM chunks_vec"
        ).fetchone()["rowid"]
        self.assertEqual(vec_rowid, result.chunk_rowids[0])

    def test_multi_chunk_rowid_join_is_consistent(self) -> None:
        chunks = [_chunk(i, f"chunk-{i}") for i in range(5)]
        result = store_memory_atomic(
            self.db,
            namespace="diary/2025",
            content="five paragraphs",
            content_hash="h-5",
            chunks=chunks,
        )
        counts = self.db.row_counts()
        self.assertEqual(counts, {"memories": 1, "chunks_meta": 5, "chunks_vec": 5})

        joined = self.db.conn.execute(
            "SELECT cm.rowid, cm.chunk_index "
            "FROM chunks_meta cm JOIN chunks_vec cv ON cv.rowid = cm.rowid "
            "ORDER BY cm.chunk_index"
        ).fetchall()
        self.assertEqual([r["chunk_index"] for r in joined], [0, 1, 2, 3, 4])
        self.assertEqual(tuple(r["rowid"] for r in joined), result.chunk_rowids)

    def test_two_memories_accumulate_independently(self) -> None:
        r1 = store_memory_atomic(
            self.db, namespace="n", content="a", content_hash="ha",
            chunks=[_chunk(0, "a0"), _chunk(1, "a1")],
        )
        r2 = store_memory_atomic(
            self.db, namespace="n", content="b", content_hash="hb",
            chunks=[_chunk(0, "b0")],
        )
        self.assertNotEqual(r1.memory_id, r2.memory_id)
        self.assertEqual(self.db.row_counts(),
                         {"memories": 2, "chunks_meta": 3, "chunks_vec": 3})


class FaultInjectionTests(unittest.TestCase):
    """For every fault point, the DB must be unchanged after rollback."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Database(Path(self.tmp.name) / "t1.db")
        self._seed = store_memory_atomic(
            self.db, namespace="seed", content="pre-existing",
            content_hash="hseed",
            chunks=[_chunk(0, "seed-0"), _chunk(1, "seed-1")],
        )
        self.baseline = self.db.row_counts()

    def tearDown(self) -> None:
        self.db.close()
        self.tmp.cleanup()

    def _run_fault(self, fault: FaultPoint) -> None:
        with self.assertRaises(AtomicStoreError):
            store_memory_atomic(
                self.db, namespace="abort", content="should-not-land",
                content_hash="habort",
                chunks=[_chunk(0, "x"), _chunk(1, "y"), _chunk(2, "z")],
                fault=fault,
            )
        self.assertEqual(
            self.db.row_counts(), self.baseline,
            f"fault {fault.value} left dirty rows",
        )
        orphan_meta = self.db.conn.execute(
            "SELECT COUNT(*) FROM chunks_meta cm "
            "LEFT JOIN memories m ON m.id = cm.memory_id WHERE m.id IS NULL"
        ).fetchone()[0]
        orphan_vec = self.db.conn.execute(
            "SELECT COUNT(*) FROM chunks_vec cv "
            "LEFT JOIN chunks_meta cm ON cm.rowid = cv.rowid "
            "WHERE cm.rowid IS NULL"
        ).fetchone()[0]
        self.assertEqual((orphan_meta, orphan_vec), (0, 0))

    def test_rollback_at_every_fault_point(self) -> None:
        for fp in iter_fault_points():
            with self.subTest(fault=fp):
                self._run_fault(fp)

    def test_db_remains_writable_after_rollback(self) -> None:
        with self.assertRaises(AtomicStoreError):
            store_memory_atomic(
                self.db, namespace="abort", content="x", content_hash="h",
                chunks=[_chunk(0)], fault=FaultPoint.AFTER_VEC_INSERT,
            )
        r = store_memory_atomic(
            self.db, namespace="ok", content="later", content_hash="hok",
            chunks=[_chunk(0, "later")],
        )
        counts = self.db.row_counts()
        self.assertEqual(counts["memories"], self.baseline["memories"] + 1)
        self.assertEqual(counts["chunks_meta"], self.baseline["chunks_meta"] + 1)
        self.assertEqual(counts["chunks_vec"], self.baseline["chunks_vec"] + 1)
        self.assertIsInstance(r.memory_id, int)


class InputValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.db = Database(":memory:")

    def tearDown(self) -> None:
        self.db.close()

    def test_empty_chunks_rejected(self) -> None:
        with self.assertRaises(AtomicStoreError):
            store_memory_atomic(
                self.db, namespace="n", content="x", content_hash="h", chunks=[],
            )
        self.assertEqual(self.db.row_counts(),
                         {"memories": 0, "chunks_meta": 0, "chunks_vec": 0})

    def test_duplicate_chunk_index_rejected(self) -> None:
        with self.assertRaises(AtomicStoreError):
            store_memory_atomic(
                self.db, namespace="n", content="x", content_hash="h",
                chunks=[_chunk(0), _chunk(0)],
            )
        self.assertEqual(self.db.row_counts(),
                         {"memories": 0, "chunks_meta": 0, "chunks_vec": 0})

    def test_non_bytes_embedding_rejected(self) -> None:
        bad = ChunkInput(content="x", embedding="not-bytes", chunk_index=0)  # type: ignore[arg-type]
        with self.assertRaises(AtomicStoreError):
            store_memory_atomic(
                self.db, namespace="n", content="x", content_hash="h", chunks=[bad],
            )

    def test_sqlite_error_triggers_rollback(self) -> None:
        with self.db.transaction() as conn:
            conn.execute(
                "INSERT INTO memories (namespace, content, content_hash) "
                "VALUES ('n','c','hdup')"
            )
        self.db.conn.execute("CREATE UNIQUE INDEX tmp_u ON memories(content_hash);")
        baseline = self.db.row_counts()
        with self.assertRaises(AtomicStoreError):
            store_memory_atomic(
                self.db, namespace="n", content="c2", content_hash="hdup",
                chunks=[_chunk(0)],
            )
        self.assertEqual(self.db.row_counts(), baseline)


if __name__ == "__main__":
    unittest.main()
