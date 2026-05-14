"""Reranker clients.

OllamaRerankerClient — targets the native ``/api/rerank`` endpoint (not yet
available in Ollama as of 2026-Q2).  Kept as an integration surface for when
the endpoint ships.

EmbeddingReranker — cosine-similarity rerank using *any* embedding model.
No extra dependencies, no new model to download.  Works with Ollama's
``/api/embed`` today.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Protocol, cast
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

RERANK_TIMEOUT_SECONDS = 10.0
RERANK_RETRY_COUNT = 0
DEFAULT_RERANK_MODEL = "qwen3-reranker-0.6b:latest"


class RerankError(RuntimeError):
    """Raised when the rerank endpoint fails or returns invalid data."""


class HttpResponse(Protocol):
    def __enter__(self) -> HttpResponse: ...
    def __exit__(self, exc_type: object, exc: object, tb: object) -> None: ...
    def read(self) -> bytes: ...


class HttpPoster(Protocol):
    def __call__(self, request: Request, *, timeout: float) -> HttpResponse: ...


def _default_poster(request: Request, *, timeout: float) -> HttpResponse:
    return cast(HttpResponse, urlopen(request, timeout=timeout))


@dataclass(frozen=True)
class RerankResult:
    index: int
    document: str
    score: float


@dataclass(frozen=True)
class OllamaRerankerClient:
    base_url: str
    model: str = DEFAULT_RERANK_MODEL
    timeout: float = RERANK_TIMEOUT_SECONDS
    retry_count: int = RERANK_RETRY_COUNT
    poster: HttpPoster = _default_poster

    def __post_init__(self) -> None:
        if self.timeout != RERANK_TIMEOUT_SECONDS:
            raise ValueError("rerank timeout must remain 10 seconds")
        if self.retry_count != RERANK_RETRY_COUNT:
            raise ValueError("rerank retry_count must remain 0")
        if not self.base_url.strip():
            raise ValueError("base_url must not be empty")
        if not self.model.strip():
            raise ValueError("model must not be empty")

    def rerank(self, query: str, documents: list[str], *, top_n: int | None = None) -> list[RerankResult]:
        if not query.strip():
            raise ValueError("query must not be empty")
        if not documents:
            return []
        if top_n is not None and top_n <= 0:
            raise ValueError("top_n must be positive when provided")

        payload: dict[str, object] = {
            "model": self.model,
            "query": query,
            "documents": documents,
        }
        if top_n is not None:
            payload["top_n"] = top_n

        request = Request(
            _join_url(self.base_url, "/api/rerank"),
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with self.poster(request, timeout=self.timeout) as response:
                body = response.read().decode("utf-8")
        except HTTPError as exc:
            if exc.code == 404:
                raise RerankError("rerank endpoint is unavailable on this Ollama version") from exc
            raise RerankError(f"rerank endpoint returned HTTP {exc.code}") from exc
        except URLError as exc:
            raise RerankError(f"rerank endpoint unavailable: {exc.reason}") from exc
        except TimeoutError as exc:
            raise RerankError("rerank endpoint timed out") from exc

        try:
            data = cast(object, json.loads(body))
        except json.JSONDecodeError as exc:
            raise RerankError("rerank endpoint returned invalid JSON") from exc

        return _extract_results(data, documents)


def _join_url(base_url: str, path: str) -> str:
    return base_url.rstrip("/") + path


def _extract_results(data: object, documents: list[str]) -> list[RerankResult]:
    if not isinstance(data, dict):
        raise RerankError("rerank response must be a JSON object")

    payload = cast(dict[str, object], data)
    raw_results = payload.get("results")
    if raw_results is None:
        raw_results = payload.get("scores")

    if not isinstance(raw_results, list) or not raw_results:
        raise RerankError("rerank response did not contain ranked results")

    results: list[RerankResult] = []
    if raw_results and isinstance(raw_results[0], dict):
        for item in cast(list[object], raw_results):
            if not isinstance(item, dict):
                raise RerankError("rerank result entries must be objects")
            row = cast(dict[str, object], item)
            index_raw = row.get("index")
            if not isinstance(index_raw, int):
                raise RerankError("rerank result entries must include integer index")
            if index_raw < 0 or index_raw >= len(documents):
                raise RerankError(f"rerank result index out of range: {index_raw}")
            score_raw = row.get("relevance_score", row.get("score"))
            if not isinstance(score_raw, int | float):
                raise RerankError("rerank result entries must include a numeric score")
            results.append(RerankResult(index=index_raw, document=documents[index_raw], score=float(score_raw)))
        return sorted(results, key=lambda item: (-item.score, item.index))

    if all(isinstance(item, int | float) for item in raw_results):
        scores = cast(list[object], raw_results)
        if len(scores) != len(documents):
            raise RerankError("score list length must match document list length")
        for index, score in enumerate(scores):
            results.append(RerankResult(index=index, document=documents[index], score=float(cast(int | float, score))))
        return sorted(results, key=lambda item: (-item.score, item.index))

    raise RerankError("unsupported rerank response shape")


# ══════════════════════════════════════════════════════════════════════
#  EmbeddingReranker  —  cosine-similarity rerank using the same embedding model.
#  Works today with Ollama (no /api/rerank endpoint required).
# ══════════════════════════════════════════════════════════════════════

import math as _math
from .embeddings import OllamaEmbeddingClient


class EmbeddingReranker:
    """Rerank documents by cosine similarity to the query.

    Uses *any* embedding model accessible through ``OllamaEmbeddingClient``.
    No separate reranker model needed — the same embedding space that powers
    S1 vector search is reused here.

    Batch embeds all documents in a single API call (~1s for 45 texts).
    """

    def __init__(self, embed_client: OllamaEmbeddingClient):
        self._ec = embed_client

    def rerank(
        self,
        query: str,
        documents: list[str],
        *,
        top_n: int | None = None,
    ) -> list[RerankResult]:
        if not query.strip():
            raise ValueError("query must not be empty")
        if not documents:
            return []
        if top_n is not None and top_n <= 0:
            raise ValueError("top_n must be positive")

        # Embed query once, then batch-embed all documents.
        qv = self._ec.embed(query)
        dvs = self._ec.embed_batch(documents)

        results: list[RerankResult] = []
        for idx, dv in enumerate(dvs):
            dot = sum(a * b for a, b in zip(qv, dv))
            norm_q = _math.sqrt(sum(a * a for a in qv))
            norm_d = _math.sqrt(sum(a * a for a in dv))
            score = dot / (norm_q * norm_d) if norm_q * norm_d > 0 else 0.0
            results.append(RerankResult(index=idx, document=documents[idx], score=score))

        results.sort(key=lambda r: -r.score)
        if top_n is not None:
            results = results[:top_n]
        return results
