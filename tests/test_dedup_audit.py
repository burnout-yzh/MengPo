from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from memory_mcp.dedup_audit import append_dedup_audit_event, make_dedup_audit_event


class DedupAuditTests(unittest.TestCase):
    def test_append_event(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            log = Path(td) / "dedup_audit.jsonl"
            event = make_dedup_audit_event(
                namespace="demo",
                incoming_content_hash="abc",
                reviewed_memory_id=5,
                similarity=0.99,
                verdict="duplicate",
                action="reject",
                reason="duplicate_confirmed_by_review",
                merge_target_file=None,
            )
            append_dedup_audit_event(log, event)
            payload = json.loads(log.read_text(encoding="utf-8").splitlines()[0])
            self.assertEqual(payload["action"], "reject")
            self.assertEqual(payload["reviewed_memory_id"], 5)


if __name__ == "__main__":
    unittest.main(verbosity=2)
