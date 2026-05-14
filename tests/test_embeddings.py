from __future__ import annotations

import unittest
from dataclasses import dataclass
from urllib.error import URLError
from urllib.request import Request

from memory_mcp.embeddings import (
    EMBEDDING_RETRY_COUNT,
    EMBEDDING_TIMEOUT_SECONDS,
    EmbeddingError,
    OllamaEmbeddingClient,
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
        self.body: bytes = body if body is not None else b'{"embedding":[1,2,3]}'
        self.error: BaseException | None = error
        self.calls: list[tuple[Request, float]] = []

    def __call__(self, request: Request, *, timeout: float) -> FakeResponse:
        self.calls.append((request, timeout))
        if self.error is not None:
            raise self.error
        return FakeResponse(self.body)


class EmbeddingClientTests(unittest.TestCase):
    def test_uses_fixed_timeout_and_single_post(self) -> None:
        poster = FakePoster()
        client = OllamaEmbeddingClient("http://ollama.local", poster=poster)

        vector = client.embed("hello")

        self.assertEqual(vector, [1.0, 2.0, 3.0])
        self.assertEqual(len(poster.calls), 1)
        request, timeout = poster.calls[0]
        self.assertEqual(timeout, EMBEDDING_TIMEOUT_SECONDS)
        self.assertEqual(request.full_url, "http://ollama.local/api/embeddings")

    def test_accepts_embeddings_response_shape(self) -> None:
        poster = FakePoster(b'{"embeddings":[[0.25,0.5]]}')
        client = OllamaEmbeddingClient("http://ollama.local/", poster=poster)

        self.assertEqual(client.embed("hello"), [0.25, 0.5])

    def test_rejects_policy_override(self) -> None:
        with self.assertRaises(ValueError):
            _ = OllamaEmbeddingClient("http://ollama.local", timeout=9.0)
        with self.assertRaises(ValueError):
            _ = OllamaEmbeddingClient("http://ollama.local", retry_count=1)
        self.assertEqual(EMBEDDING_RETRY_COUNT, 0)

    def test_failure_does_not_retry(self) -> None:
        poster = FakePoster(error=URLError("down"))
        client = OllamaEmbeddingClient("http://ollama.local", poster=poster)

        with self.assertRaises(EmbeddingError):
            _ = client.embed("hello")

        self.assertEqual(len(poster.calls), 1)

    def test_invalid_shape_is_rejected(self) -> None:
        poster = FakePoster(b'{"embedding":["bad"]}')
        client = OllamaEmbeddingClient("http://ollama.local", poster=poster)

        with self.assertRaises(EmbeddingError):
            _ = client.embed("hello")


if __name__ == "__main__":
    _ = unittest.main()
