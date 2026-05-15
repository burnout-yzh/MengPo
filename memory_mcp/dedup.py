"""T11/T12/T13 dedup adjudication policy helpers.

High-similarity candidates are never auto-dropped. They must be reviewed and
then routed to either reject (true duplicate) or merge/append flow
(false positive).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from .config import Config


# ── dedup threshold from bowl.yaml ────────────────────────────────────
DEFAULT_DEDUP_THRESHOLD = Config.load_cached().dedup.threshold


class ReviewVerdict(str, Enum):
    DUPLICATE = "duplicate"
    FALSE_POSITIVE = "false_positive"


@dataclass(frozen=True)
class SimilarityCandidate:
    memory_id: int
    namespace: str
    similarity: float
    source_file: str | None


@dataclass(frozen=True)
class DedupResolution:
    should_store: bool
    should_reject: bool
    should_merge_append: bool
    rejected_reason: str | None
    merge_target_file: str | None


def requires_review(similarity: float, *, threshold: float = DEFAULT_DEDUP_THRESHOLD) -> bool:
    """Return True when a chunk must enter LLM adjudication route."""
    if threshold < 0 or threshold > 1:
        raise ValueError("threshold must be in [0, 1]")
    return similarity >= threshold


def default_merge_target(*, source_file: str | None, namespace: str) -> str:
    """Resolve append/edit fallback target for false-positive merge flow."""
    if source_file and source_file.strip():
        return source_file
    normalized_namespace = namespace.strip().replace("/", "_")
    if not normalized_namespace:
        normalized_namespace = "default"
    return f"{normalized_namespace}_inbox.md"


def resolve_review(
    candidate: SimilarityCandidate,
    *,
    verdict: ReviewVerdict,
) -> DedupResolution:
    """Convert adjudication verdict into store/reject/merge action."""
    if verdict is ReviewVerdict.DUPLICATE:
        return DedupResolution(
            should_store=False,
            should_reject=True,
            should_merge_append=False,
            rejected_reason="duplicate_confirmed_by_review",
            merge_target_file=None,
        )
    return DedupResolution(
        should_store=False,
        should_reject=False,
        should_merge_append=True,
        rejected_reason=None,
        merge_target_file=default_merge_target(
            source_file=candidate.source_file,
            namespace=candidate.namespace,
        ),
    )
