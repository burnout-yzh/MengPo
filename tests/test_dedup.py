from __future__ import annotations

import unittest

from memory_mcp.dedup import (
    DEFAULT_DEDUP_THRESHOLD,
    ReviewVerdict,
    SimilarityCandidate,
    default_merge_target,
    requires_review,
    resolve_review,
)


class DedupPolicyTests(unittest.TestCase):
    def test_requires_review_at_threshold(self) -> None:
        self.assertTrue(requires_review(DEFAULT_DEDUP_THRESHOLD))
        self.assertFalse(requires_review(DEFAULT_DEDUP_THRESHOLD - 0.01))

    def test_threshold_bounds_validation(self) -> None:
        with self.assertRaises(ValueError):
            _ = requires_review(0.9, threshold=-0.1)
        with self.assertRaises(ValueError):
            _ = requires_review(0.9, threshold=1.1)

    def test_default_merge_target_prefers_source_file(self) -> None:
        self.assertEqual(
            default_merge_target(source_file="docs/a.md", namespace="projects/demo"),
            "docs/a.md",
        )

    def test_default_merge_target_falls_back_to_namespace_inbox(self) -> None:
        self.assertEqual(
            default_merge_target(source_file=None, namespace="projects/demo"),
            "projects_demo_inbox.md",
        )

    def test_duplicate_verdict_rejects(self) -> None:
        resolution = resolve_review(
            SimilarityCandidate(
                memory_id=1,
                namespace="n",
                similarity=0.99,
                source_file="docs/a.md",
            ),
            verdict=ReviewVerdict.DUPLICATE,
        )
        self.assertFalse(resolution.should_store)
        self.assertTrue(resolution.should_reject)
        self.assertFalse(resolution.should_merge_append)
        self.assertEqual(resolution.rejected_reason, "duplicate_confirmed_by_review")

    def test_false_positive_verdict_routes_to_merge_append(self) -> None:
        resolution = resolve_review(
            SimilarityCandidate(
                memory_id=1,
                namespace="projects/demo",
                similarity=0.99,
                source_file=None,
            ),
            verdict=ReviewVerdict.FALSE_POSITIVE,
        )
        self.assertFalse(resolution.should_store)
        self.assertFalse(resolution.should_reject)
        self.assertTrue(resolution.should_merge_append)
        self.assertEqual(resolution.merge_target_file, "projects_demo_inbox.md")


if __name__ == "__main__":
    unittest.main(verbosity=2)
