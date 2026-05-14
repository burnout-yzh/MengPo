"""Retrieval ranking policy (T6).
Naihe_Bridge (奈何桥) + Samsara_Rank (轮回排序).

Semantic relevance is the gate and primary signal upstream. Freshness only
re-ranks inside the semantic candidate set, using a weighted geometric mean.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from math import exp, log
import json
import sqlite3
from .embeddings import OllamaEmbeddingClient
from .database import Database
from .freshness import WangYou_Decay


class ProtocolErrorCode(str, Enum):
    INVALID_PAYLOAD_TYPE = "invalid_payload_type"
    INVALID_KEY_TYPE = "invalid_key_type"
    INVALID_MEMORY_ID = "invalid_memory_id"
    INVALID_VALUE = "invalid_value"
    MISSING_MEMORY_IDS = "missing_memory_ids"
    UNKNOWN_MEMORY_IDS = "unknown_memory_ids"


class RetrievalProtocolError(ValueError):
    """Raised when the S2 `memory_id -> 0|1` payload is invalid."""

    def __init__(self, code: ProtocolErrorCode, message: str):
        super().__init__(message)
        self.code = code

SEMANTIC_CANDIDATE_LIMIT = 45  # S1 full pool: blend-sort all 45, deliver in 5-chunk batches
RESULT_LIMIT = 5
FRESHNESS_WEIGHT = 0.368  # 1/e -- natural decay constant
RANK_SCORE_EPSILON = 1e-12


@dataclass(frozen=True)
class RetrievalCandidate:
    memory_id: int
    content: str
    semantic_score: float
    freshness_score: float
    source_file: str | None = None
    paragraph_start: int | None = None
    paragraph_end: int | None = None


@dataclass(frozen=True)
class RankedMemory:
    memory_id: int
    content: str
    semantic_score: float
    freshness_score: float
    rank_before: int
    rank_after: int
    source_file: str | None = None
    paragraph_start: int | None = None
    paragraph_end: int | None = None


@dataclass(frozen=True)
class S1Delivery:
    """Payload delivered to S2 for a single retrieval round."""

    results: list[RankedMemory]
    delivered_ids: tuple[int, ...]


@dataclass(frozen=True)
class S3WritebackPlan:
    """Write-back decision produced from one validated S2 response."""

    delivered_count: int
    effective_ids: tuple[int, ...]
    all_invalid: bool


@dataclass(frozen=True)
class RetrievalRoundOutcome:
    """Round-level outcome used by T10 branch handling."""

    delivered: S1Delivery
    protocol_valid: bool
    writeback_plan: S3WritebackPlan | None



def S1_vector_search(
    db: Database,
    query: str,
    candidate_limit: int = SEMANTIC_CANDIDATE_LIMIT,
    embed_client: OllamaEmbeddingClient | None = None,
    now: datetime | None = None,
) -> list[RetrievalCandidate]:
    """S1 vector search via sqlite-vec (Naihe_Bridge physical layer).

    Single-transaction pipeline:
    1. vec search → rowid + distance pairs
    2. Batch JOIN chunks_meta + memories → content + freshness anchors
    3. WangYou_Decay populates freshness_score for downstream S2 blending
    """
    if embed_client is None:
        embed_client = OllamaEmbeddingClient(
            base_url="http://127.0.0.1:11434",
            model="qwen3-embedding-0.6b",
        )
    if now is None:
        now = datetime.now(UTC)

    query_vec = embed_client.embed(query)
    query_json = json.dumps(query_vec, separators=(",", ":"))

    # ── Step 1: vec search (single transaction) ──
    with db.transaction() as conn:
        try:
            rows = conn.execute(
                "SELECT rowid, distance FROM chunks_vec WHERE embedding MATCH ? ORDER BY distance LIMIT ?",
                (query_json, candidate_limit),
            ).fetchall()
        except sqlite3.OperationalError as exc:
            raise RuntimeError(f"sqlite-vec search failed: {exc}") from exc

        if not rows:
            return []

        # ── Step 2: batch JOIN to collect content + freshness anchors ──
        rowid_set: list[int] = []
        distance_by_rowid: dict[int, float] = {}
        for rowid_val, distance in rows:
            rowid_set.append(rowid_val)
            distance_by_rowid[rowid_val] = distance

        placeholders = ",".join(["?"] * len(rowid_set))
        content_rows = conn.execute(
            f"""
            SELECT cm.rowid, m.id, m.content, m.source_file,
                   m.last_effective_recall_at, m.created_at
              FROM chunks_meta cm
              JOIN memories m ON m.id = cm.memory_id
             WHERE cm.rowid IN ({placeholders})
            """,
            rowid_set,
        ).fetchall()

    # ── Step 3: build candidates with real freshness ──
    # Sort to match original vec distance order (closest first).
    content_by_rowid = {row["rowid"]: row for row in content_rows}
    results: list[RetrievalCandidate] = []
    for rowid_val in rowid_set:
        cr = content_by_rowid.get(rowid_val)
        if cr is None:
            continue
        distance = distance_by_rowid[rowid_val]
        similarity = max(0.0, min(1.0, 1.0 - distance))

        # Compute WangYou_Decay freshness from last effective recall anchor.
        # Fall back to created_at when last_effective_recall_at is NULL (virgin memory).
        anchor_text = cr["last_effective_recall_at"] or cr["created_at"]
        try:
            anchor_dt = datetime.fromisoformat(anchor_text.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            anchor_dt = now
        freshness = WangYou_Decay(now=now, last_effective_recall_at=anchor_dt)

        results.append(RetrievalCandidate(
            memory_id=cr["id"],
            content=cr["content"],
            semantic_score=similarity,
            freshness_score=freshness,
            source_file=cr["source_file"],
        ))

    if results:
        scores = [r.semantic_score for r in results]
        fresh_vals = [r.freshness_score for r in results]
        print(f"[S1_Naihe_Bridge] vec search: {len(results)} candidates, "
              f"sim range: {min(scores):.4f} - {max(scores):.4f}, "
              f"freshness range: {min(fresh_vals):.4f} - {max(fresh_vals):.4f}")

    return results


class SessionDeliveryState:
    """Tracks judged memory ids per session for expand filtering."""

    def __init__(self) -> None:
        self._judged_by_session: dict[str, set[int]] = {}

    def excluded_ids(self, session_id: str) -> set[int]:
        return set(self._judged_by_session.get(session_id, set()))

    def record_judged_ids(self, session_id: str, memory_ids: list[int]) -> None:
        if session_id not in self._judged_by_session:
            self._judged_by_session[session_id] = set()
        self._judged_by_session[session_id].update(memory_ids)

    def clear_session(self, session_id: str) -> None:
        self._judged_by_session.pop(session_id, None)


def Samsara_Rank(  # 真名: rank_for_retrieval() — freshness x semantics re-rank
    candidates: list[RetrievalCandidate],
    *,
    candidate_limit: int = SEMANTIC_CANDIDATE_LIMIT,
    result_limit: int = RESULT_LIMIT,
    freshness_weight: float = FRESHNESS_WEIGHT,
) -> list[RankedMemory]:
    """Return retrieval results.

    The algorithm first keeps the top semantic candidates, then blends semantic
    and freshness scores with a weighted geometric mean inside that bounded set.
    Returns at most five entries; if fewer semantic candidates exist, all are
    returned.
    """
    if candidate_limit == 0 or candidate_limit < -1:
        raise ValueError("candidate_limit must be > 0 or -1")
    if result_limit == 0 or result_limit < -1:
        raise ValueError("result_limit must be > 0 or -1")
    if not (0.0 <= freshness_weight <= 1.0):
        raise ValueError("freshness_weight must be in [0, 1]")

    semantic_candidates = sorted(
        candidates,
        key=lambda item: (-item.semantic_score, item.memory_id),
    )[:_effective_limit(candidate_limit)]

    ranked = sorted(
        enumerate(semantic_candidates, start=1),
        key=lambda item: (
            -_blend_rank_score(
                semantic_score=item[1].semantic_score,
                freshness_score=item[1].freshness_score,
                freshness_weight=freshness_weight,
            ),
            item[0],
        ),
    )[:_effective_limit(result_limit)]

    return [
        RankedMemory(
            memory_id=candidate.memory_id,
            content=candidate.content,
            semantic_score=candidate.semantic_score,
            freshness_score=candidate.freshness_score,
            rank_before=rank_before,
            rank_after=rank_after,
            source_file=candidate.source_file,
            paragraph_start=candidate.paragraph_start,
            paragraph_end=candidate.paragraph_end,
        )
        for rank_after, (rank_before, candidate) in enumerate(ranked, start=1)
    ]


# Samsara_Rank internal: weighted geometric mean
def _blend_rank_score(
        *, semantic_score: float, freshness_score: float, freshness_weight: float) -> float:
    """Blend normalized semantic/freshness scores with a weighted geometric mean.

    `freshness_weight` acts as the slider: semantic weight is `1 - freshness_weight`.
    """

    semantic_weight = 1.0 - freshness_weight
    semantic = max(RANK_SCORE_EPSILON, min(1.0, semantic_score))
    freshness = max(RANK_SCORE_EPSILON, min(1.0, freshness_score))
    return exp(semantic_weight * log(semantic) + freshness_weight * log(freshness))


def Naihe_Bridge(  # 真名: build_s1_delivery() — S1 semantic gate
    candidates: list[RetrievalCandidate],
    *,
    excluded_memory_ids: set[int] | None = None,
    candidate_limit: int = SEMANTIC_CANDIDATE_LIMIT,
    result_limit: int = RESULT_LIMIT,
    freshness_weight: float = FRESHNESS_WEIGHT,
) -> S1Delivery:
    """Build one S1 delivery list, optionally excluding previously judged ids."""
    excluded = excluded_memory_ids if excluded_memory_ids is not None else set()
    filtered = [c for c in candidates if c.memory_id not in excluded]
    ranked = Samsara_Rank(
        filtered,
        candidate_limit=candidate_limit,
        result_limit=result_limit,
        freshness_weight=freshness_weight,
    )
    delivered_ids = tuple(item.memory_id for item in ranked)
    return S1Delivery(results=ranked, delivered_ids=delivered_ids)


def _effective_limit(limit: int) -> int | None:
    """Translate `-1` to unlimited for candidate/result limits."""
    if limit == -1:
        return None
    if limit <= 0:
        raise ValueError("limit must be > 0 or -1")
    return limit


def validate_s2_effectiveness_map(
    delivered_ids: tuple[int, ...],
    effectiveness_map: dict[str, int],
) -> dict[int, bool]:
    """Validate a full 0/1 map and return a typed bool map keyed by memory id."""
    if not isinstance(effectiveness_map, dict):
        raise RetrievalProtocolError(
            ProtocolErrorCode.INVALID_PAYLOAD_TYPE,
            "S2 payload must be a JSON object mapping memory_id to 0/1",
        )

    parsed: dict[int, bool] = {}
    for key, value in effectiveness_map.items():
        if not isinstance(key, str):
            raise RetrievalProtocolError(
                ProtocolErrorCode.INVALID_KEY_TYPE,
                "S2 payload keys must be strings",
            )
        try:
            memory_id = int(key)
        except ValueError as exc:
            raise RetrievalProtocolError(
                ProtocolErrorCode.INVALID_MEMORY_ID,
                f"invalid memory_id key: {key}",
            ) from exc
        if memory_id <= 0:
            raise RetrievalProtocolError(
                ProtocolErrorCode.INVALID_MEMORY_ID,
                f"memory_id must be positive: {memory_id}",
            )
        if value not in (0, 1):
            raise RetrievalProtocolError(
                ProtocolErrorCode.INVALID_VALUE,
                f"memory_id {memory_id} has invalid value: {value}",
            )
        parsed[memory_id] = bool(value)

    delivered_set = set(delivered_ids)
    payload_set = set(parsed.keys())
    missing = delivered_set - payload_set
    if missing:
        raise RetrievalProtocolError(
            ProtocolErrorCode.MISSING_MEMORY_IDS,
            f"S2 payload missing memory_ids: {sorted(missing)}",
        )
    unknown = payload_set - delivered_set
    if unknown:
        raise RetrievalProtocolError(
            ProtocolErrorCode.UNKNOWN_MEMORY_IDS,
            f"S2 payload contains unknown memory_ids: {sorted(unknown)}",
        )

    return parsed


def make_s3_writeback_plan(validated_map: dict[int, bool]) -> S3WritebackPlan:
    """Create a write-back plan: only effective ids are eligible."""
    effective_ids = tuple(sorted([memory_id for memory_id, effective in validated_map.items() if effective]))
    delivered_count = len(validated_map)
    return S3WritebackPlan(
        delivered_count=delivered_count,
        effective_ids=effective_ids,
        all_invalid=len(effective_ids) == 0,
    )


def process_retrieval_round(
    candidates: list[RetrievalCandidate],
    *,
    s2_effectiveness_map: dict[str, int] | None,
    excluded_memory_ids: set[int] | None = None,
    candidate_limit: int = SEMANTIC_CANDIDATE_LIMIT,
    result_limit: int = RESULT_LIMIT,
    freshness_weight: float = FRESHNESS_WEIGHT,
) -> RetrievalRoundOutcome:
    """End-to-end T7/T10 helper for one round.

    - No-hit: delivered ids is empty and writeback plan is None.
    - Protocol failure: raises RetrievalProtocolError.
    - All-invalid: writeback plan exists with `all_invalid=True`.
    """
    delivered = Naihe_Bridge(
        candidates,
        excluded_memory_ids=excluded_memory_ids,
        candidate_limit=candidate_limit,
        result_limit=result_limit,
        freshness_weight=freshness_weight,
    )
    if not delivered.delivered_ids:
        return RetrievalRoundOutcome(delivered=delivered, protocol_valid=True, writeback_plan=None)
    if s2_effectiveness_map is None:
        raise RetrievalProtocolError(
            ProtocolErrorCode.INVALID_PAYLOAD_TYPE,
            "S2 payload is required when S1 delivered at least one memory",
        )

    validated = validate_s2_effectiveness_map(delivered.delivered_ids, s2_effectiveness_map)
    return RetrievalRoundOutcome(
        delivered=delivered,
        protocol_valid=True,
        writeback_plan=make_s3_writeback_plan(validated),
    )
