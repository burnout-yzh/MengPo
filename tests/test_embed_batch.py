"""Tests for batch embedding (embed_batch)."""

from __future__ import annotations

import io
import json
import unittest
from urllib.error import HTTPError, URLError
from urllib.request import Request

from memory_mcp.embeddings import (
    EMBEDDING_TIMEOUT_SECONDS,
    EmbeddingError,
    OllamaEmbeddingClient,
)


class FakeBatchResponse:
    def __init__(self, body: bytes):
        self.body = body

    def __enter__(self) -> "FakeBatchResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def read(self) -> bytes:
        return self.body


class FakeBatchPoster:
    def __init__(self, body: bytes | None = None, error: BaseException | None = None):
        self.body = body if body is not None else _batch_json(3, dim=4)
        self.error = error
        self.calls: list[tuple[Request, float]] = []

    def __call__(self, request: Request, *, timeout: float) -> FakeBatchResponse:
        self.calls.append((request, timeout))
        if self.error is not None:
            raise self.error
        return FakeBatchResponse(self.body)


def _batch_json(count: int, dim: int = 1024) -> bytes:
    vec = [0.5] * dim
    return json.dumps({"embeddings": [vec] * count}).encode("utf-8")


class EmbedBatchTests(unittest.TestCase):
    def test_batch_returns_correct_count(self) -> None:
        poster = FakeBatchPoster(_batch_json(5))
        client = OllamaEmbeddingClient("http://ollama.local", poster=poster)
        vecs = client.embed_batch(["a", "b", "c", "d", "e"])
        self.assertEqual(len(vecs), 5)
        self.assertEqual(len(vecs[0]), 1024)

    def test_batch_uses_embed_endpoint(self) -> None:
        poster = FakeBatchPoster(_batch_json(2))
        client = OllamaEmbeddingClient("http://ollama.local", poster=poster)
        client.embed_batch(["x", "y"])
        request, _ = poster.calls[0]
        self.assertIn("/api/embed", request.full_url)

    def test_batch_empty_input_returns_empty(self) -> None:
        poster = FakeBatchPoster()
        client = OllamaEmbeddingClient("http://ollama.local", poster=poster)
        self.assertEqual(client.embed_batch([]), [])

    def test_batch_empty_strings_raise(self) -> None:
        poster = FakeBatchPoster()
        client = OllamaEmbeddingClient("http://ollama.local", poster=poster)
        with self.assertRaises(ValueError):
            client.embed_batch(["valid", ""])

    def test_batch_count_mismatch_raises(self) -> None:
        poster = FakeBatchPoster(_batch_json(1))  # sent 1, asked for 3
        client = OllamaEmbeddingClient("http://ollama.local", poster=poster)
        with self.assertRaises(EmbeddingError):
            client.embed_batch(["a", "b", "c"])

    def test_batch_http_error_raises(self) -> None:
        error = HTTPError("http://ollama.local/api/embed", 500, "err", hdrs=None, fp=io.BytesIO(b""))
        poster = FakeBatchPoster(error=error)
        client = OllamaEmbeddingClient("http://ollama.local", poster=poster)
        with self.assertRaises(EmbeddingError):
            client.embed_batch(["a"])

    def test_batch_timeout_raises(self) -> None:
        poster = FakeBatchPoster(error=TimeoutError())
        client = OllamaEmbeddingClient("http://ollama.local", poster=poster)
        with self.assertRaises(EmbeddingError):
            client.embed_batch(["a"])

    def test_batch_response_not_json_raises(self) -> None:
        poster = FakeBatchPoster(b"not json")
        client = OllamaEmbeddingClient("http://ollama.local", poster=poster)
        with self.assertRaises(EmbeddingError):
            client.embed_batch(["a"])

    def test_batch_response_not_dict_raises(self) -> None:
        poster = FakeBatchPoster(b"[]")
        client = OllamaEmbeddingClient("http://ollama.local", poster=poster)
        with self.assertRaises(EmbeddingError):
            client.embed_batch(["a"])

    def test_batch_keep_alive_passed_when_set(self) -> None:
        poster = FakeBatchPoster(_batch_json(1))
        client = OllamaEmbeddingClient("http://ollama.local", poster=poster, keep_alive=0)
        client.embed_batch(["a"])
        request, _ = poster.calls[0]
        payload = json.loads(request.data)
        self.assertEqual(payload.get("keep_alive"), 0)

    def test_batch_keep_alive_omitted_when_none(self) -> None:
        poster = FakeBatchPoster(_batch_json(1))
        client = OllamaEmbeddingClient("http://ollama.local", poster=poster, keep_alive=None)
        client.embed_batch(["a"])
        request, _ = poster.calls[0]
        payload = json.loads(request.data)
        self.assertNotIn("keep_alive", payload)
