"""Tests for EmbeddingReranker (cosine-similarity based)."""

from __future__ import annotations

import io
import json
import unittest
from urllib.request import Request

from memory_mcp.embeddings import OllamaEmbeddingClient
from memory_mcp.reranker import EmbeddingReranker, RerankResult


class FakeEmbedResponse:
    def __init__(self, body: bytes):
        self.body = body

    def __enter__(self) -> "FakeEmbedResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def read(self) -> bytes:
        return self.body


def _fake_query_vec(dim: int = 4) -> dict[str, list[float]]:
    """Query vector — distinct direction for testing."""
    return {"embedding": [1.0, 0.0, 0.0, 0.0] + [0.0] * (dim - 4)}


def _fake_match_vec(dim: int = 4) -> dict[str, list[float]]:
    """Near-identical to query — should score high."""
    return {"embedding": [0.99, 0.01, 0.0, 0.0] + [0.0] * (dim - 4)}


def _fake_far_vec(dim: int = 4) -> dict[str, list[float]]:
    """Orthogonal to query — should score low."""
    return {"embedding": [0.0, 1.0, 0.0, 0.0] + [0.0] * (dim - 4)}


class FakeEmbeddingClient:
    """Simulates OllamaEmbeddingClient for EmbeddingReranker tests."""

    def __init__(self, dim: int = 1024):
        self.dim = dim
        self._embed_calls: list[str] = []

    def embed(self, text: str) -> list[float]:
        self._embed_calls.append(text)
        if text == "query":
            return _fake_query_vec(self.dim)["embedding"]
        if text.startswith("match"):
            return _fake_match_vec(self.dim)["embedding"]
        return _fake_far_vec(self.dim)["embedding"]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        self._embed_calls.extend(texts)
        result = []
        for t in texts:
            if "match" in t:
                result.append(_fake_match_vec(self.dim)["embedding"])
            else:
                result.append(_fake_far_vec(self.dim)["embedding"])
        return result


class EmbeddingRerankerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.ec = FakeEmbeddingClient(dim=4)
        self.rr = EmbeddingReranker(self.ec)

    def test_rerank_returns_correct_count(self) -> None:
        results = self.rr.rerank("query", ["far a", "match b", "far c"])
        self.assertEqual(len(results), 3)

    def test_rerank_sorts_by_score_desc(self) -> None:
        results = self.rr.rerank("query", ["far a", "match b", "far c", "far d"])
        scores = [r.score for r in results]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_rerank_top_n_truncates(self) -> None:
        results = self.rr.rerank("query", ["far a", "match b", "far c"], top_n=2)
        self.assertEqual(len(results), 2)

    def test_rerank_match_scores_higher(self) -> None:
        results = self.rr.rerank("query", ["far a", "match b"])
        match_score = [r.score for r in results if "match" in r.document][0]
        far_score = [r.score for r in results if "far" in r.document][0]
        self.assertGreater(match_score, far_score)

    def test_rerank_empty_input(self) -> None:
        self.assertEqual(self.rr.rerank("query", []), [])

    def test_rerank_empty_query_raises(self) -> None:
        with self.assertRaises(ValueError):
            self.rr.rerank("", ["doc"])

    def test_rerank_bad_top_n_raises(self) -> None:
        with self.assertRaises(ValueError):
            self.rr.rerank("query", ["doc"], top_n=0)
        with self.assertRaises(ValueError):
            self.rr.rerank("query", ["doc"], top_n=-1)
