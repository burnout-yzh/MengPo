from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from memory_mcp import Database
from memory_mcp.dedup import ReviewVerdict
from memory_mcp.store_flow import apply_merge_append, orchestrate_store_memory


class StoreFlowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Database(Path(self.tmp.name) / "store_flow.db")

    def tearDown(self) -> None:
        self.db.close()
        self.tmp.cleanup()

    def test_store_when_no_similarity_hit(self) -> None:
        result = orchestrate_store_memory(
            db=self.db,
            namespace="demo",
            content="hello",
            embedding=[0.1] + [0.0] * 1023,
            best_similarity=None,
            best_memory_id=None,
            review_verdict=None,
        )
        self.assertTrue(result.stored)
        self.assertFalse(result.skipped)
        self.assertIsNotNone(result.memory_id)

    def test_skip_when_duplicate_reviewed(self) -> None:
        audit_log = Path(self.tmp.name) / "dedup_audit.jsonl"
        result = orchestrate_store_memory(
            db=self.db,
            namespace="demo",
            content="dup",
            embedding=[0.1] + [0.0] * 1023,
            best_similarity=0.99,
            best_memory_id=5,
            review_verdict=ReviewVerdict.DUPLICATE,
            dedup_audit_log_file=audit_log,
        )
        self.assertFalse(result.stored)
        self.assertTrue(result.skipped)
        self.assertEqual(result.reason, "duplicate_confirmed_by_review")
        event = json.loads(audit_log.read_text(encoding="utf-8").splitlines()[0])
        self.assertEqual(event["action"], "reject")

    def test_skip_and_route_merge_append_when_false_positive(self) -> None:
        audit_log = Path(self.tmp.name) / "dedup_audit.jsonl"
        result = orchestrate_store_memory(
            db=self.db,
            namespace="projects/demo",
            content="new info",
            embedding=[0.1] + [0.0] * 1023,
            best_similarity=0.99,
            best_memory_id=6,
            review_verdict=ReviewVerdict.FALSE_POSITIVE,
            source_file=None,
            dedup_audit_log_file=audit_log,
        )
        self.assertFalse(result.stored)
        self.assertTrue(result.skipped)
        self.assertEqual(result.reason, "merge_append_required")
        self.assertEqual(result.merge_target_file, "projects_demo_inbox.md")
        event = json.loads(audit_log.read_text(encoding="utf-8").splitlines()[0])
        self.assertEqual(event["action"], "merge_append")

    def test_apply_merge_append_writes_marker_and_content(self) -> None:
        target = apply_merge_append(
            root_dir=self.tmp.name,
            merge_target_file="projects_demo_inbox.md",
            incoming_content="new line",
            memory_id=6,
        )
        text = target.read_text(encoding="utf-8")
        self.assertIn("merged_from_memory_id: 6", text)
        self.assertIn("new line", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
