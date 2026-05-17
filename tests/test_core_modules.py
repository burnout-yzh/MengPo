from __future__ import annotations

import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
UTC = timezone.utc
from pathlib import Path

import json
from memory_mcp import ChunkInput, Database, store_memory_atomic
from memory_mcp.freshness import FreshnessParams, WangYou_Decay
from memory_mcp.scanner import scan_memory_dir
from scripts.inject_memory import scan_markdown_files
from memory_mcp.telemetry import append_event, append_round_event, make_event, make_round_event


def _vec(seed: int = 0, dim: int = 1024) -> bytes:
    """Generate dummy embedding vector for vec0."""
    v = [float(seed % 256) / 256.0] * dim
    import json; return json.dumps(v, separators=(",", ":")).encode()

def _chunk(i: int, text: str = "hello", dim: int = 4) -> ChunkInput:
    return ChunkInput(
        content=text,
        embedding=_vec(0),
        chunk_index=i,
        paragraph_start=i,
        paragraph_end=i + 1,
    )


class SoftDeleteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Database(Path(self.tmp.name) / "core.db")
        self.r1 = store_memory_atomic(
            self.db,
            namespace="projects/demo",
            content="active",
            content_hash="h1",
            chunks=[_chunk(0)],
        )
        self.r2 = store_memory_atomic(
            self.db,
            namespace="projects/demo",
            content="to-delete",
            content_hash="h2",
            chunks=[_chunk(1)],
        )

    def tearDown(self) -> None:
        self.db.close()
        self.tmp.cleanup()

    def test_default_list_hides_soft_deleted(self) -> None:
        self.assertTrue(self.db.soft_delete_memory(self.r2.memory_id))
        visible = self.db.list_memories(namespace="projects/demo")
        all_rows = self.db.list_memories(namespace="projects/demo", include_deleted=True)
        self.assertEqual(len(visible), 1)
        self.assertEqual(visible[0]["id"], self.r1.memory_id)
        self.assertEqual(len(all_rows), 2)


class FreshnessTests(unittest.TestCase):
    def test_freshness_monotonic_decay(self) -> None:
        now = datetime.now(UTC)
        params = FreshnessParams(initial_strength=1.0, half_life_days=7.0, shrink_factor=1.0, floor=0.01)
        s0 = WangYou_Decay(now=now, last_effective_recall_at=now, params=params)
        s7 = WangYou_Decay(now=now, last_effective_recall_at=now - timedelta(days=7), params=params)
        s30 = WangYou_Decay(now=now, last_effective_recall_at=now - timedelta(days=30), params=params)
        self.assertGreaterEqual(s0, s7)
        self.assertGreaterEqual(s7, s30)
        self.assertGreaterEqual(s30, params.floor)


class ScannerTests(unittest.TestCase):
    def test_skip_symlink_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            docs = root / "docs"
            docs.mkdir()
            (docs / "a.md").write_text("# A\n", encoding="utf-8")
            outside = Path(td).parent / (Path(td).name + "_outside.md")
            outside.write_text("# outside\n", encoding="utf-8")
            try:
                (docs / "link_out.md").symlink_to(outside)
            except OSError:
                self.skipTest("OS does not support unprivileged symlink creation")
            try:
                result = scan_memory_dir(docs)
                self.assertEqual(len(result.files), 1)
                self.assertEqual(result.files[0].name, "a.md")
                self.assertGreaterEqual(len(result.skipped_symlinks), 1)
            finally:
                if outside.exists():
                    outside.unlink()


class TelemetryTests(unittest.TestCase):
    def test_append_event_contains_required_fields(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            log_file = Path(td) / "retrieval_events.jsonl"
            event = make_event(
                query="hello",
                namespace="n",
                memory_id=1,
                semantic_score=0.9,
                WangYou_Decay=0.8,
                rank_before=2,
                rank_after=1,
                s2_effective=True,
                s3_written_back=True,
            )
            append_event(log_file, event)
            line = log_file.read_text(encoding="utf-8").strip()
            self.assertIn('"semantic_score": 0.9', line)
            self.assertIn('"WangYou_Decay": 0.8', line)
            self.assertIn('"s2_effective": true', line)
            self.assertIn('"s3_written_back": true', line)

    def test_append_round_event_contains_required_fields(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            log_file = Path(td) / "rounds.jsonl"
            event = make_round_event(
                session_id="s1",
                query="hello",
                namespace="n",
                delivered_count=5,
                effective_count=2,
                writeback_count=2,
                all_invalid=False,
                protocol_valid=True,
                protocol_error_code=None,
                expand=True,
            )
            append_round_event(log_file, event)
            line = log_file.read_text(encoding="utf-8").strip()
            self.assertIn('"session_id": "s1"', line)
            self.assertIn('"delivered_count": 5', line)
            self.assertIn('"effective_count": 2', line)
            self.assertIn('"writeback_count": 2', line)
            self.assertIn('"protocol_valid": true', line)
            self.assertIn('"expand": true', line)


class InjectionWhitelistTests(unittest.TestCase):
    def test_scan_markdown_files_whitelist_dirs_and_files(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "memory").mkdir()
            (root / "skills").mkdir()
            (root / "notes").mkdir()

            (root / "memory" / "a.md").write_text("a", encoding="utf-8")
            (root / "skills" / "skill.md").write_text("s", encoding="utf-8")
            (root / "notes" / "n.md").write_text("n", encoding="utf-8")
            (root / "top.md").write_text("t", encoding="utf-8")

            files = scan_markdown_files(
                root,
                "*.md",
                whitelist_files=["top.md"],
                whitelist_dirs=["memory", "notes"],
            )

            rels = {f.relative_to(root).as_posix() for f in files}
            self.assertEqual(rels, {"memory/a.md", "notes/n.md", "top.md"})

    def test_scan_markdown_files_whitelist_files_case_insensitive(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "memory").mkdir()
            (root / "Memory.MD").write_text("root", encoding="utf-8")
            (root / "memory" / "a.md").write_text("a", encoding="utf-8")

            files = scan_markdown_files(
                root,
                "*.md",
                whitelist_files=["memory.md"],
                whitelist_dirs=["memory"],
            )

            rels = {f.relative_to(root).as_posix() for f in files}
            self.assertEqual(rels, {"Memory.MD", "memory/a.md"})


if __name__ == "__main__":
    unittest.main(verbosity=2)
