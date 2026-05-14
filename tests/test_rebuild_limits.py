from __future__ import annotations

import unittest

from memory_mcp.rebuild_limits import (
    RebuildScanLimits,
    RebuildScanStats,
    evaluate_rebuild_limits,
)


class RebuildLimitsTests(unittest.TestCase):
    def test_warn_when_warn_limit_exceeded(self) -> None:
        stats = RebuildScanStats(total_files=300_000, total_bytes=10)
        result = evaluate_rebuild_limits(stats, RebuildScanLimits())
        self.assertTrue(result.warn)
        self.assertFalse(result.blocked)

    def test_block_when_hard_limit_exceeded(self) -> None:
        stats = RebuildScanStats(total_files=1_000_001, total_bytes=10)
        result = evaluate_rebuild_limits(stats, RebuildScanLimits())
        self.assertFalse(result.warn)
        self.assertTrue(result.blocked)
        self.assertEqual(result.reason, "hard_max_files")

    def test_minus_one_means_unlimited(self) -> None:
        stats = RebuildScanStats(total_files=10_000_000, total_bytes=10_000_000_000_000)
        limits = RebuildScanLimits(
            warn_max_files=-1,
            hard_max_files=-1,
            warn_max_bytes=-1,
            hard_max_bytes=-1,
        )
        result = evaluate_rebuild_limits(stats, limits)
        self.assertFalse(result.warn)
        self.assertFalse(result.blocked)


if __name__ == "__main__":
    unittest.main(verbosity=2)
