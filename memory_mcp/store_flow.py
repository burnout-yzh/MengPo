"""Store orchestration flow for dedup preflight and atomic write."""

from __future__ import annotations

import hashlib
import json
import logging
import threading
from dataclasses import dataclass
from pathlib import Path

from .atomic_store import ChunkInput, StoreResult, store_memory_atomic
from .database import Database
from .dedup import DEFAULT_DEDUP_THRESHOLD, ReviewVerdict
from .dedup_audit import append_dedup_audit_event, make_dedup_audit_event
from .embeddings import OllamaEmbeddingClient
from .store_preflight import PreflightResult, run_store_preflight


_logger = logging.getLogger(__name__)
_merge_append_lock = threading.Lock()


def _resolve_merge_target(root_dir: str | Path, merge_target_file: str) -> Path:
    root = Path(root_dir).expanduser().resolve()
    target = (root / merge_target_file).resolve()
    if target != root and root not in target.parents:
        raise ValueError(f"merge target escapes root: {merge_target_file}")
    return target


@dataclass(frozen=True)
class StoreFlowResult:
    stored: bool
    skipped: bool
    reason: str | None
    memory_id: int | None
    chunk_rowids: tuple[int, ...]
    merge_target_file: str | None


def build_single_chunk_input(content: str, embedding: list[float]) -> ChunkInput:
    """Build one chunk payload for current proof-of-contract flow."""
    if not embedding:
        raise ValueError("embedding must not be empty")
    payload_str = json.dumps(embedding, separators=(",", ":"))  # vec0 expects JSON string
    return ChunkInput(content=content, embedding=payload_str.encode("utf-8"), chunk_index=0)


def compute_content_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def orchestrate_store_memory(
    *,
    db: Database,
    namespace: str,
    content: str,
    embedding: list[float],
    best_similarity: float | None,
    best_memory_id: int | None,
    review_verdict: ReviewVerdict | None,
    source_file: str | None = None,
    metadata: dict[str, object] | None = None,
    dedup_threshold: float = DEFAULT_DEDUP_THRESHOLD,
    dedup_audit_log_file: str | Path | None = None,
) -> StoreFlowResult:
    """Run preflight dedup policy then atomic store when allowed."""
    preflight: PreflightResult = run_store_preflight(
        namespace=namespace,
        source_file=source_file,
        best_similarity=best_similarity,
        best_memory_id=best_memory_id,
        review_verdict=review_verdict,
        threshold=dedup_threshold,
    )
    if preflight.skipped:
        if dedup_audit_log_file is not None and preflight.reviewed_candidate is not None and preflight.reason is not None:
            candidate = preflight.reviewed_candidate
            action = "reject" if preflight.reason == "duplicate_confirmed_by_review" else "merge_append"
            verdict = "duplicate" if action == "reject" else "false_positive"
            try:
                append_dedup_audit_event(
                    dedup_audit_log_file,
                    make_dedup_audit_event(
                        namespace=namespace,
                        incoming_content_hash=compute_content_hash(content),
                        reviewed_memory_id=candidate.memory_id,
                        similarity=candidate.similarity,
                        verdict=verdict,
                        action=action,
                        reason=preflight.reason,
                        merge_target_file=preflight.merge_target_file,
                    ),
                )
            except Exception as exc:
                _logger.warning("dedup audit append failed: %s", exc)
        return StoreFlowResult(
            stored=False,
            skipped=True,
            reason=preflight.reason,
            memory_id=None,
            chunk_rowids=(),
            merge_target_file=preflight.merge_target_file,
        )

    chunk = build_single_chunk_input(content, embedding)
    stored: StoreResult = store_memory_atomic(
        db,
        namespace=namespace,
        content=content,
        content_hash=compute_content_hash(content),
        chunks=[chunk],
        source_file=source_file,
        metadata=metadata,
    )
    return StoreFlowResult(
        stored=True,
        skipped=False,
        reason=None,
        memory_id=stored.memory_id,
        chunk_rowids=stored.chunk_rowids,
        merge_target_file=None,
    )


def apply_merge_append(
    *,
    root_dir: str | Path,
    merge_target_file: str,
    incoming_content: str,
    memory_id: int,
) -> Path:
    """Append content to merge target with provenance marker.

    For now this is a straightforward append action; future versions may do
    semantic editing before append.
    """
    target = _resolve_merge_target(root_dir, merge_target_file)
    target.parent.mkdir(parents=True, exist_ok=True)
    marker = f"\n\n---\nmerged_from_memory_id: {memory_id}\n"
    with _merge_append_lock:
        with target.open("a", encoding="utf-8") as f:
            f.write(marker)
            f.write(incoming_content)
            if not incoming_content.endswith("\n"):
                f.write("\n")
    return target
