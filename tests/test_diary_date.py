"""Test _extract_diary_date — smart diary date extraction."""

from __future__ import annotations

import unittest

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.inject_memory import _extract_diary_date


class DiaryDateExtractionTests(unittest.TestCase):
    # ── YYYY-MM-DD (with and without suffixes) ──

    def test_standard_diary(self) -> None:
        self.assertEqual(
            _extract_diary_date("2026-05-14.md"),
            "2026-05-14T00:00:00.000Z",
        )

    def test_with_description(self) -> None:
        self.assertEqual(
            _extract_diary_date("2026-05-14-something.md"),
            "2026-05-14T00:00:00.000Z",
        )

    def test_with_time(self) -> None:
        self.assertEqual(
            _extract_diary_date("2026-03-19-0820.md"),
            "2026-03-19T08:20:00.000Z",
        )

    def test_single_digit_month_day(self) -> None:
        self.assertEqual(
            _extract_diary_date("2026-1-5.md"),
            "2026-01-05T00:00:00.000Z",
        )

    def test_single_digit_month_day_with_time(self) -> None:
        self.assertEqual(
            _extract_diary_date("2026-3-7-1430.md"),
            "2026-03-07T14:30:00.000Z",
        )

    # ── Underscore separators ──

    def test_underscore_format(self) -> None:
        self.assertEqual(
            _extract_diary_date("2026_05_14_notes.md"),
            "2026-05-14T00:00:00.000Z",
        )

    def test_underscore_with_time(self) -> None:
        self.assertEqual(
            _extract_diary_date("2026_05_14_1430.md"),
            "2026-05-14T14:30:00.000Z",
        )

    # ── US format: MM-DD-YYYY ──

    def test_us_format(self) -> None:
        self.assertEqual(
            _extract_diary_date("05-14-2026.md"),
            "2026-05-14T00:00:00.000Z",
        )

    def test_us_compact(self) -> None:
        self.assertEqual(
            _extract_diary_date("05142026.md"),
            "2026-05-14T00:00:00.000Z",
        )

    # ── Compact: YYYYMMDD ──

    def test_compact_ymd(self) -> None:
        self.assertEqual(
            _extract_diary_date("20260514.md"),
            "2026-05-14T00:00:00.000Z",
        )

    def test_compact_ymd_with_time(self) -> None:
        self.assertEqual(
            _extract_diary_date("20260514_1430.md"),
            "2026-05-14T14:30:00.000Z",
        )

    # ── No date ──

    def test_no_date_in_name(self) -> None:
        self.assertIsNone(_extract_diary_date("architecture-decisions.md"))

    def test_no_date_in_name_appendix(self) -> None:
        self.assertIsNone(_extract_diary_date("api-pricing.md"))

    # ── Invalid dates ──

    def test_invalid_month(self) -> None:
        self.assertIsNone(_extract_diary_date("2026-13-01.md"))

    def test_invalid_day(self) -> None:
        self.assertIsNone(_extract_diary_date("2026-02-30.md"))

    def test_invalid_year_too_old(self) -> None:
        self.assertIsNone(_extract_diary_date("1999-01-01-backup.md"))

    # ── Path components ──

    def test_path_with_date(self) -> None:
        self.assertEqual(
            _extract_diary_date("memory/2026-05-14.md"),
            "2026-05-14T00:00:00.000Z",
        )

    def test_windows_path_with_date(self) -> None:
        self.assertEqual(
            _extract_diary_date("D:\\memory\\2026-05-14.md"),
            "2026-05-14T00:00:00.000Z",
        )

    # ── Time edge cases ──

    def test_time_invalid_hour(self) -> None:
        """2459 → hour 24 is invalid, so time should be ignored (fall to 00:00)."""
        result = _extract_diary_date("2026-05-14-2459.md")
        # Hour 24 invalid → _try_time returns None → falls back to 00:00
        self.assertEqual(result, "2026-05-14T00:00:00.000Z")

    def test_time_invalid_minute(self) -> None:
        """1260 → minute 60 invalid."""
        result = _extract_diary_date("2026-05-14-1260.md")
        self.assertEqual(result, "2026-05-14T00:00:00.000Z")

    def test_time_midnight(self) -> None:
        self.assertEqual(
            _extract_diary_date("2026-05-14-0000.md"),
            "2026-05-14T00:00:00.000Z",
        )

    def test_time_full_hour(self) -> None:
        self.assertEqual(
            _extract_diary_date("2026-05-14-2300.md"),
            "2026-05-14T23:00:00.000Z",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
