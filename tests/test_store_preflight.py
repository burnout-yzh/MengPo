from __future__ import annotations

import unittest

import json
from memory_mcp.dedup import ReviewVerdict
import json
from memory_mcp.store_preflight import run_store_preflight


class StorePreflightTests(unittest.TestCase):
    def test_no_similarity_hit_allows_store(self) -> None:
        result = run_store_preflight(
            namespace="projects/demo",
            source_file="docs/a.md",
            best_similarity=None,
            best_memory_id=None,
            review_verdict=None,
            threshold=0.95,
        )
        self.assertTrue(result.stored)
        self.assertFalse(result.skipped)

    def test_below_threshold_allows_store_without_review(self) -> None:
        result = run_store_preflight(
            namespace="projects/demo",
            source_file="docs/a.md",
            best_similarity=0.8,
            best_memory_id=1,
            review_verdict=None,
            threshold=0.95,
        )
        self.assertTrue(result.stored)
        self.assertFalse(result.skipped)

    def test_requires_review_without_verdict_rejected(self) -> None:
        with self.assertRaises(ValueError):
            _ = run_store_preflight(
                namespace="projects/demo",
                source_file="docs/a.md",
                best_similarity=0.99,
                best_memory_id=1,
                review_verdict=None,
                threshold=0.95,
            )

    def test_duplicate_verdict_skips_store(self) -> None:
        result = run_store_preflight(
            namespace="projects/demo",
            source_file="docs/a.md",
            best_similarity=0.99,
            best_memory_id=1,
            review_verdict=ReviewVerdict.DUPLICATE,
            threshold=0.95,
        )
        self.assertFalse(result.stored)
        self.assertTrue(result.skipped)
        self.assertEqual(result.reason, "duplicate_confirmed_by_review")
        self.assertIsNone(result.merge_target_file)

    def test_false_positive_verdict_routes_to_merge_append(self) -> None:
        result = run_store_preflight(
            namespace="projects/demo",
            source_file=None,
            best_similarity=0.99,
            best_memory_id=1,
            review_verdict=ReviewVerdict.FALSE_POSITIVE,
            threshold=0.95,
        )
        self.assertFalse(result.stored)
        self.assertTrue(result.skipped)
        self.assertEqual(result.reason, "merge_append_required")
        self.assertEqual(result.merge_target_file, "projects_demo_inbox.md")


if __name__ == "__main__":
    unittest.main(verbosity=2)
