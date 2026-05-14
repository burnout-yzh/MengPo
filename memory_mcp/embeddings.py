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
DEFAULT_EMBEDDING_MODEL = "qwen3-embedding-0.6b"


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
    keep_alive: int | float | None = None  # seconds: 0=unload immediately, None=use Ollama default (5m)

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

        payload_dict: dict[str, object] = {"model": self.model, "prompt": text}
        if self.keep_alive is not None:
            payload_dict["keep_alive"] = self.keep_alive
        payload = json.dumps(payload_dict).encode("utf-8")
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

    def unload(self) -> None:
        """Tell Ollama to immediately unload the model from GPU memory.

        Sends a trivial embedding request with ``keep_alive=0``.
        Use at the end of batch injection scripts.
        """
        payload = json.dumps(
            {"model": self.model, "input": ".", "keep_alive": 0}
        ).encode("utf-8")
        request = Request(
            _join_url(self.base_url, "/api/embed"),
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with self.poster(request, timeout=self.timeout) as _:
                pass
        except Exception:
            pass  # Best-effort — don't crash if Ollama is already gone.

    # ══ batch embedding  ══════════════════════════════════════════════

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed multiple texts in a single API call.

        Uses Ollama's ``/api/embed`` endpoint with ``"input"`` array.
        Measured ~1s for 45 texts (qwen3-embedding-0.6b) vs ~5.8s when
        calling ``embed()`` 45 times sequentially.
        """
        if not texts:
            return []
        if any(not t for t in texts):
            raise ValueError("all texts in batch must be non-empty")

        payload_dict: dict[str, object] = {"model": self.model, "input": texts}
        if self.keep_alive is not None:
            payload_dict["keep_alive"] = self.keep_alive
        payload = json.dumps(payload_dict).encode("utf-8")
        request = Request(
            _join_url(self.base_url, "/api/embed"),
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with self.poster(request, timeout=self.timeout) as response:
                body = response.read().decode("utf-8")
        except HTTPError as exc:
            raise EmbeddingError(f"batch embedding returned HTTP {exc.code}") from exc
        except URLError as exc:
            raise EmbeddingError(f"batch embedding unavailable: {exc.reason}") from exc
        except TimeoutError as exc:
            raise EmbeddingError("batch embedding timed out") from exc

        try:
            data = cast(object, json.loads(body))
        except json.JSONDecodeError as exc:
            raise EmbeddingError("batch embedding returned invalid JSON") from exc

        return _extract_batch_embeddings(data, expected_count=len(texts))


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


def _extract_batch_embeddings(data: object, *, expected_count: int) -> list[list[float]]:
    """Parse Ollama ``/api/embed`` batch response.

    Expected shape: ``{"embeddings": [[f, ...], [f, ...], ...]}``
    """
    if not isinstance(data, dict):
        raise EmbeddingError("batch embedding response must be a JSON object")

    raw = cast(dict[str, object], data).get("embeddings")
    if not isinstance(raw, list) or len(raw) != expected_count:
        raise EmbeddingError(
            f"expected {expected_count} embeddings, got {len(raw) if isinstance(raw, list) else type(raw).__name__}"
        )

    result: list[list[float]] = []
    for entry in cast(list[object], raw):
        if not isinstance(entry, list):
            raise EmbeddingError("each batch entry must be a float list")
        vec: list[float] = []
        for v in cast(list[object], entry):
            if not isinstance(v, int | float):
                raise EmbeddingError("embedding values must be numbers")
            vec.append(float(v))
        result.append(vec)
    return result
