from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import json
from memory_mcp import ChunkInput, Database, store_memory_atomic
import json
from memory_mcp.retrieval import RetrievalCandidate, RetrievalProtocolError
import json
from memory_mcp.retrieval_service import RetrievalService


def _vec(seed: int = 0, dim: int = 1024) -> bytes:
    """Generate dummy embedding vector for vec0."""
    v = [float(seed % 256) / 256.0] * dim
    import json; return json.dumps(v, separators=(",", ":")).encode()

def _chunk(i: int) -> ChunkInput:
    return ChunkInput(content=f"c{i}", embedding=_vec(0), chunk_index=i)


class RetrievalServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Database(Path(self.tmp.name) / "retrieval_service.db")
        self.r1 = store_memory_atomic(self.db, namespace="demo", content="m1", content_hash="h1", chunks=[_chunk(0)])
        self.r2 = store_memory_atomic(self.db, namespace="demo", content="m2", content_hash="h2", chunks=[_chunk(1)])
        self.log = Path(self.tmp.name) / "round.jsonl"
        prompts_root = Path(self.tmp.name) / "memory_test_files"
        prompts_root.mkdir()
        for name in ("AGENTS.md", "MEMORY.md", "PROFILE.md", "SOUL.md"):
            (prompts_root / name).write_text(f"{name} prompt", encoding="utf-8")
        self.svc = RetrievalService(
            db=self.db,
            telemetry_log_file=self.log,
            enable_duoshe=True,
            duoshe_root=prompts_root,
        )

    def tearDown(self) -> None:
        self.db.close()
        self.tmp.cleanup()

    def test_no_hit_round(self) -> None:
        result = self.svc.run_round(
            session_id="s1",
            query="q",
            namespace="demo",
            candidates=[],
            s2_effectiveness_map=None,
            expand=False,
        )
        self.assertEqual(result.delivered_ids, ())
        self.assertEqual(result.writeback_count, 0)
        self.assertEqual(len(result.duoshe_prompts), 4)

    def test_protocol_fail(self) -> None:
        cands = [RetrievalCandidate(self.r1.memory_id, "m1", 0.9, 0.1)]
        with self.assertRaises(RetrievalProtocolError):
            _ = self.svc.run_round(
                session_id="s1",
                query="q",
                namespace="demo",
                candidates=cands,
                s2_effectiveness_map={str(self.r1.memory_id): 2},
                expand=False,
            )

    def test_expand_and_writeback(self) -> None:
        cands = [
            RetrievalCandidate(self.r1.memory_id, "m1", 0.9, 0.1),
            RetrievalCandidate(self.r2.memory_id, "m2", 0.8, 0.1),
        ]
        first = self.svc.run_round(
            session_id="s1",
            query="q1",
            namespace="demo",
            candidates=cands,
            s2_effectiveness_map={str(self.r1.memory_id): 1, str(self.r2.memory_id): 0},
            expand=False,
        )
        self.assertEqual(first.writeback_count, 1)
        self.assertEqual(len(first.duoshe_prompts), 4)

        second = self.svc.run_round(
            session_id="s1",
            query="q2",
            namespace="demo",
            candidates=cands,
            s2_effectiveness_map=None,
            expand=True,
        )
        self.assertEqual(second.delivered_ids, ())
        self.assertEqual(second.duoshe_prompts, ())

    def test_reset_session_reinjects_duoshe_prompts(self) -> None:
        first = self.svc.run_round(
            session_id="s-reinject",
            query="q",
            namespace="demo",
            candidates=[],
            s2_effectiveness_map=None,
            expand=False,
        )
        self.assertEqual(len(first.duoshe_prompts), 4)
        self.svc.reset_session("s-reinject")
        second = self.svc.run_round(
            session_id="s-reinject",
            query="q2",
            namespace="demo",
            candidates=[],
            s2_effectiveness_map=None,
            expand=False,
        )
        self.assertEqual(len(second.duoshe_prompts), 4)


class RetrievalServiceDuosheDisabledTests(unittest.TestCase):
    def test_duoshe_disabled_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            db = Database(Path(td) / "disabled.db")
            try:
                svc = RetrievalService(db=db, telemetry_log_file=Path(td) / "round.jsonl")
                result = svc.run_round(
                    session_id="s1",
                    query="q",
                    namespace="demo",
                    candidates=[],
                    s2_effectiveness_map=None,
                    expand=False,
                )
                self.assertEqual(result.duoshe_prompts, ())
            finally:
                db.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
