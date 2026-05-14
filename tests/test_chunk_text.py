"""Tests for chunk_text with cumulative merge + sentence-boundary splitting."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts.inject_memory import chunk_text


class ChunkTextTests(unittest.TestCase):
    def test_short_paragraphs_merge_to_min_size(self) -> None:
        """Three short paragraphs should merge into one chunk when sum < min+max."""
        text = "## Title\n\nA short line.\n\nAnother one."
        chunks = chunk_text(text, max_size=500, min_size=80)
        self.assertEqual(len(chunks), 1)
        self.assertGreater(len(chunks[0]), 30)

    def test_hr_boundary_is_skipped(self) -> None:
        """Horizontal rules flush buffer — the HR itself is skipped, content is split."""
        text = "content before\n\n---\n\ncontent after"
        chunks = chunk_text(text, max_size=500, min_size=80)
        # HR boundary splits content: "content before" + "content after" = 2 chunks
        self.assertEqual(len(chunks), 2)
        self.assertFalse(any("---" in c for c in chunks),
                         "HR should not appear in any chunk")

    def test_code_fence_is_standalone(self) -> None:
        """Code fences should flush the buffer and become standalone chunks."""
        text = "intro text\n\n```python\nprint('hello')\n```\n\noutro"
        chunks = chunk_text(text, max_size=500, min_size=80)
        # intro + outro merged (if sum > min), code fence standalone
        self.assertGreaterEqual(len(chunks), 2)
        self.assertTrue(any("```python" in c for c in chunks))

    def test_long_paragraph_split_at_sentence(self) -> None:
        """A paragraph exceeding max_size should split at sentence boundaries."""
        # Build ~1500 chars with sentence boundaries
        long_para = ("这是一段比较长的文本内容，其中包含句号作为分割标记。" * 30)
        text = "intro\n\n" + long_para
        chunks = chunk_text(text, max_size=500, min_size=160)
        self.assertGreaterEqual(len(chunks), 2,
                                f"Expected >=2 chunks for {len(long_para)}-char para, got {len(chunks)}")

    def test_min_size_accumulates_small_items(self) -> None:
        """Multiple very short paragraphs accumulate until min_size is reached."""
        text = "\n\n".join([f"item {i}" for i in range(10)])
        chunks = chunk_text(text, max_size=500, min_size=100)
        # Should be fewer chunks than 10
        self.assertLess(len(chunks), 10)

    def test_single_short_paragraph_stays(self) -> None:
        """A standalone short paragraph still becomes a chunk."""
        text = "lonely paragraph"
        chunks = chunk_text(text, max_size=500, min_size=80)
        # Even under min_size, if it's the only paragraph, emit it
        self.assertGreaterEqual(len(chunks), 1)

    def test_size_distribution_in_range(self) -> None:
        """With realistic Markdown, most chunks should be in [min, max] range."""
        text = (
            "## Section\n\n"
            + "This is a proper paragraph with enough content to reach min size easily.\n\n"
            + "### Subsection\n\n"
            + "Another paragraph here, also long enough to meet the minimum requirement.\n\n"
            + "---\n\n"
            + "## Another Section\n\n"
            + "And this is the final paragraph with enough text to be valid.\n\n"
        )
        chunks = chunk_text(text, max_size=500, min_size=80)
        for c in chunks:
            self.assertGreater(len(c), 30, f"Chunk too small: {len(c)} chars: {c[:50]}")

    def test_empty_input(self) -> None:
        self.assertEqual(chunk_text(""), [])
        self.assertEqual(chunk_text("\n\n\n"), [])
