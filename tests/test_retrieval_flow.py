from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timezone
UTC = timezone.utc
from pathlib import Path

from memory_mcp import ChunkInput, Database, store_memory_atomic
from memory_mcp.retrieval import RetrievalCandidate, RetrievalProtocolError, SessionDeliveryState
from memory_mcp.retrieval_flow import run_retrieval_round


def _vec(seed: int = 0, dim: int = 1024) -> bytes:
    """Generate dummy embedding vector for vec0."""
    v = [float(seed % 256) / 256.0] * dim
    import json; return json.dumps(v, separators=(",", ":")).encode()

def _chunk(i: int) -> ChunkInput:
    return ChunkInput(content=f"c{i}", embedding=_vec(0), chunk_index=i)


class RetrievalFlowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Database(Path(self.tmp.name) / "flow.db")
        self.r1 = store_memory_atomic(
            self.db,
            namespace="demo",
            content="m1",
            content_hash="h1",
            chunks=[_chunk(0)],
        )
        self.r2 = store_memory_atomic(
            self.db,
            namespace="demo",
            content="m2",
            content_hash="h2",
            chunks=[_chunk(1)],
        )
        self.log = Path(self.tmp.name) / "round.jsonl"

    def tearDown(self) -> None:
        self.db.close()
        self.tmp.cleanup()

    def test_effective_writeback_updates_memory_fields(self) -> None:
        state = SessionDeliveryState()
        candidates = [
            RetrievalCandidate(self.r1.memory_id, "m1", 0.9, 0.1),
            RetrievalCandidate(self.r2.memory_id, "m2", 0.8, 0.1),
        ]
        payload = {str(self.r1.memory_id): 1, str(self.r2.memory_id): 0}

        result = run_retrieval_round(
            db=self.db,
            session_state=state,
            session_id="s1",
            query="q",
            namespace="demo",
            candidates=candidates,
            s2_effectiveness_map=payload,
            telemetry_log_file=self.log,
            expand=False,
        )

        self.assertEqual(result.effective_ids, (self.r1.memory_id,))
        self.assertEqual(result.writeback_count, 1)
        rows = self.db.list_memories(namespace="demo", include_deleted=True)
        row_by_id = {row["id"]: row for row in rows}
        self.assertEqual(row_by_id[self.r1.memory_id]["effective_recall_count"], 1)
        self.assertIsNotNone(row_by_id[self.r1.memory_id]["last_effective_recall_at"])
        self.assertEqual(row_by_id[self.r2.memory_id]["effective_recall_count"], 0)

    def test_all_invalid_does_not_writeback(self) -> None:
        state = SessionDeliveryState()
        candidates = [RetrievalCandidate(self.r1.memory_id, "m1", 0.9, 0.1)]
        payload = {str(self.r1.memory_id): 0}

        result = run_retrieval_round(
            db=self.db,
            session_state=state,
            session_id="s1",
            query="q",
            namespace="demo",
            candidates=candidates,
            s2_effectiveness_map=payload,
            telemetry_log_file=self.log,
            expand=False,
        )
        self.assertTrue(result.all_invalid)
        self.assertEqual(result.writeback_count, 0)

    def test_protocol_error_raises_and_logs_invalid_round(self) -> None:
        state = SessionDeliveryState()
        candidates = [RetrievalCandidate(self.r1.memory_id, "m1", 0.9, 0.1)]

        with self.assertRaises(RetrievalProtocolError):
            _ = run_retrieval_round(
                db=self.db,
                session_state=state,
                session_id="s1",
                query="q",
                namespace="demo",
                candidates=candidates,
                s2_effectiveness_map={str(self.r1.memory_id): 2},
                telemetry_log_file=self.log,
                expand=False,
            )

        lines = self.log.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), 1)
        event = json.loads(lines[0])
        self.assertFalse(event["protocol_valid"])

    def test_expand_excludes_previously_judged(self) -> None:
        state = SessionDeliveryState()
        candidates = [
            RetrievalCandidate(self.r1.memory_id, "m1", 0.9, 0.1),
            RetrievalCandidate(self.r2.memory_id, "m2", 0.8, 0.1),
        ]

        first_payload = {str(self.r1.memory_id): 1, str(self.r2.memory_id): 0}
        _ = run_retrieval_round(
            db=self.db,
            session_state=state,
            session_id="s1",
            query="q1",
            namespace="demo",
            candidates=candidates,
            s2_effectiveness_map=first_payload,
            telemetry_log_file=self.log,
            expand=False,
        )

        second = run_retrieval_round(
            db=self.db,
            session_state=state,
            session_id="s1",
            query="q2",
            namespace="demo",
            candidates=candidates,
            s2_effectiveness_map=None,
            telemetry_log_file=self.log,
            expand=True,
        )
        self.assertEqual(second.delivered_ids, ())

    def test_writeback_uses_shrink_factor_reinforcement(self) -> None:
        self.db.conn.execute(
            "UPDATE memories SET created_at = ? WHERE id = ?",
            ("2026-01-01T00:00:00.000Z", self.r1.memory_id),
        )
        updated = self.db.Sansheng_Stone(
            memory_ids=[self.r1.memory_id],
            shrink_factor=0.25,
            now=datetime(2026, 1, 5, 0, 0, tzinfo=UTC),
        )
        self.assertEqual(updated, 1)
        row = [r for r in self.db.list_memories(namespace="demo", include_deleted=True) if r["id"] == self.r1.memory_id][0]
        self.assertEqual(row["last_effective_recall_at"], "2026-01-04T00:00:00.000Z")
        self.assertEqual(row["effective_recall_count"], 1)

    def test_writeback_rejects_non_positive_shrink_factor(self) -> None:
        with self.assertRaises(ValueError):
            _ = self.db.Sansheng_Stone(memory_ids=[self.r1.memory_id], shrink_factor=0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
