"""Pre-store dedup decision flow for T11/T12/T13.

This module executes policy decisions before atomic store write:
- no high-similarity hit: allow store
- high similarity + duplicate verdict: skip/reject
- high similarity + false-positive verdict: route to merge/append flow
"""

from __future__ import annotations

from dataclasses import dataclass

from .dedup import (
    DedupResolution,
    ReviewVerdict,
    SimilarityCandidate,
    requires_review,
    resolve_review,
)


@dataclass(frozen=True)
class PreflightResult:
    stored: bool
    skipped: bool
    reason: str | None
    merge_target_file: str | None
    reviewed_candidate: SimilarityCandidate | None


def run_store_preflight(
    *,
    namespace: str,
    source_file: str | None,
    best_similarity: float | None,
    best_memory_id: int | None,
    review_verdict: ReviewVerdict | None,
    threshold: float,
) -> PreflightResult:
    """Determine whether store should proceed or be routed.

    `review_verdict` is required only when `best_similarity` crosses threshold.
    """
    if best_similarity is None or best_memory_id is None:
        return PreflightResult(
            stored=True,
            skipped=False,
            reason=None,
            merge_target_file=None,
            reviewed_candidate=None,
        )

    candidate = SimilarityCandidate(
        memory_id=best_memory_id,
        namespace=namespace,
        similarity=best_similarity,
        source_file=source_file,
    )

    if not requires_review(candidate.similarity, threshold=threshold):
        return PreflightResult(
            stored=True,
            skipped=False,
            reason=None,
            merge_target_file=None,
            reviewed_candidate=None,
        )

    if review_verdict is None:
        raise ValueError("review_verdict is required when similarity requires review")

    decision: DedupResolution = resolve_review(candidate, verdict=review_verdict)
    if decision.should_reject:
        return PreflightResult(
            stored=False,
            skipped=True,
            reason=decision.rejected_reason,
            merge_target_file=None,
            reviewed_candidate=candidate,
        )

    if decision.should_merge_append:
        return PreflightResult(
            stored=False,
            skipped=True,
            reason="merge_append_required",
            merge_target_file=decision.merge_target_file,
            reviewed_candidate=candidate,
        )

    return PreflightResult(
        stored=decision.should_store,
        skipped=not decision.should_store,
        reason=None,
        merge_target_file=None,
        reviewed_candidate=candidate,
    )
