"""Ollama embedding client (T9).

The embedding call policy is intentionally strict: timeout is 10 seconds and
retry count is 0. Callers should fail fast and let the outer workflow decide
whether to retry later.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Protocol, cast
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

EMBEDDING_TIMEOUT_SECONDS = 10.0
EMBEDDING_RETRY_COUNT = 0
DEFAULT_EMBEDDING_MODEL = "bge-m3"


class EmbeddingError(RuntimeError):
    """Raised when the embedding endpoint fails or returns invalid data."""


class HttpResponse(Protocol):
    def __enter__(self) -> HttpResponse: ...
    def __exit__(self, exc_type: object, exc: object, tb: object) -> None: ...
    def read(self) -> bytes: ...


class HttpPoster(Protocol):
    def __call__(self, request: Request, *, timeout: float) -> HttpResponse: ...


def _default_poster(request: Request, *, timeout: float) -> HttpResponse:
    return cast(HttpResponse, urlopen(request, timeout=timeout))


@dataclass(frozen=True)
class OllamaEmbeddingClient:
    base_url: str
    model: str = DEFAULT_EMBEDDING_MODEL
    timeout: float = EMBEDDING_TIMEOUT_SECONDS
    retry_count: int = EMBEDDING_RETRY_COUNT
    poster: HttpPoster = _default_poster

    def __post_init__(self) -> None:
        if self.timeout != EMBEDDING_TIMEOUT_SECONDS:
            raise ValueError("embedding timeout must remain 10 seconds")
        if self.retry_count != EMBEDDING_RETRY_COUNT:
            raise ValueError("embedding retry_count must remain 0")
        if not self.base_url.strip():
            raise ValueError("base_url must not be empty")
        if not self.model.strip():
            raise ValueError("model must not be empty")

    def embed(self, text: str) -> list[float]:
        if not text:
            raise ValueError("text must not be empty")

        payload = json.dumps({"model": self.model, "prompt": text}).encode("utf-8")
        request = Request(
            _join_url(self.base_url, "/api/embeddings"),
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with self.poster(request, timeout=self.timeout) as response:
                body = response.read().decode("utf-8")
        except HTTPError as exc:
            raise EmbeddingError(f"embedding endpoint returned HTTP {exc.code}") from exc
        except URLError as exc:
            raise EmbeddingError(f"embedding endpoint unavailable: {exc.reason}") from exc
        except TimeoutError as exc:
            raise EmbeddingError("embedding endpoint timed out") from exc

        try:
            data = cast(object, json.loads(body))
        except json.JSONDecodeError as exc:
            raise EmbeddingError("embedding endpoint returned invalid JSON") from exc

        return _extract_embedding(data)


def _join_url(base_url: str, path: str) -> str:
    return base_url.rstrip("/") + path


def _extract_embedding(data: object) -> list[float]:
    if not isinstance(data, dict):
        raise EmbeddingError("embedding response must be a JSON object")

    payload = cast(dict[str, object], data)
    raw = payload.get("embedding")
    if raw is None:
        raw = payload.get("embeddings")
        if isinstance(raw, list) and raw and isinstance(raw[0], list):
            raw = cast(list[object], raw[0])

    if not isinstance(raw, list) or not raw:
        raise EmbeddingError("embedding response did not contain an embedding vector")

    values = cast(list[object], raw)
    vector: list[float] = []
    for value in values:
        if not isinstance(value, int | float):
            raise EmbeddingError("embedding vector must contain only numbers")
        vector.append(float(value))
    return vector
