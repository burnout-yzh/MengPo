from __future__ import annotations

import io
import json
import unittest
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.request import Request

from memory_mcp.reranker import (
    DEFAULT_RERANK_MODEL,
    RERANK_RETRY_COUNT,
    RERANK_TIMEOUT_SECONDS,
    OllamaRerankerClient,
    RerankError,
)


@dataclass
class FakeResponse:
    body: bytes

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None

    def read(self) -> bytes:
        return self.body


class FakePoster:
    def __init__(self, body: bytes | None = None, error: BaseException | None = None):
        self.body: bytes = body if body is not None else b'{"results":[{"index":1,"relevance_score":0.9},{"index":0,"relevance_score":0.5}]}'
        self.error: BaseException | None = error
        self.calls: list[tuple[Request, float]] = []

    def __call__(self, request: Request, *, timeout: float) -> FakeResponse:
        self.calls.append((request, timeout))
        if self.error is not None:
            raise self.error
        return FakeResponse(self.body)


class RerankerClientTests(unittest.TestCase):
    def test_uses_fixed_timeout_and_single_post(self) -> None:
        poster = FakePoster()
        client = OllamaRerankerClient("http://ollama.local", poster=poster)

        ranked = client.rerank("query", ["doc0", "doc1"])

        self.assertEqual([item.index for item in ranked], [1, 0])
        self.assertEqual(len(poster.calls), 1)
        request, timeout = poster.calls[0]
        self.assertEqual(timeout, RERANK_TIMEOUT_SECONDS)
        self.assertEqual(request.full_url, "http://ollama.local/api/rerank")

    def test_rejects_policy_override(self) -> None:
        with self.assertRaises(ValueError):
            _ = OllamaRerankerClient("http://ollama.local", timeout=9.0)
        with self.assertRaises(ValueError):
            _ = OllamaRerankerClient("http://ollama.local", retry_count=1)
        self.assertEqual(RERANK_RETRY_COUNT, 0)

    def test_rejects_empty_query_or_bad_top_n(self) -> None:
        client = OllamaRerankerClient("http://ollama.local", poster=FakePoster())
        with self.assertRaises(ValueError):
            _ = client.rerank("", ["doc"])
        with self.assertRaises(ValueError):
            _ = client.rerank("query", ["doc"], top_n=0)

    def test_failure_is_clear_on_404(self) -> None:
        error = HTTPError("http://ollama.local/api/rerank", 404, "not found", hdrs=None, fp=io.BytesIO(b""))
        client = OllamaRerankerClient("http://ollama.local", poster=FakePoster(error=error))

        with self.assertRaises(RerankError):
            _ = client.rerank("query", ["doc"])

    def test_invalid_shape_is_rejected(self) -> None:
        poster = FakePoster(b'{"results":[{"index":9,"relevance_score":0.1}]}')
        client = OllamaRerankerClient("http://ollama.local", poster=poster)

        with self.assertRaises(RerankError):
            _ = client.rerank("query", ["doc0", "doc1"])

    def test_accepts_score_list_shape(self) -> None:
        poster = FakePoster(b'{"scores":[0.2,0.8]}')
        client = OllamaRerankerClient("http://ollama.local/", poster=poster)

        ranked = client.rerank("query", ["doc0", "doc1"])

        self.assertEqual([item.index for item in ranked], [1, 0])
        self.assertEqual([item.document for item in ranked], ["doc1", "doc0"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
