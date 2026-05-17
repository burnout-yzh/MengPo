"""Audit helpers for T13 true-duplicate rejection records."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
UTC = timezone.utc
from pathlib import Path


_VALID_VERDICTS = {"duplicate", "false_positive"}
_VALID_ACTIONS = {"reject", "merge_append"}


@dataclass(frozen=True)
class DedupAuditEvent:
    namespace: str
    incoming_content_hash: str
    reviewed_memory_id: int
    similarity: float
    verdict: str
    action: str
    reason: str
    merge_target_file: str | None
    created_at: str


def make_dedup_audit_event(
    *,
    namespace: str,
    incoming_content_hash: str,
    reviewed_memory_id: int,
    similarity: float,
    verdict: str,
    action: str,
    reason: str,
    merge_target_file: str | None,
) -> DedupAuditEvent:
    if verdict not in _VALID_VERDICTS:
        raise ValueError(f"invalid verdict: {verdict}")
    if action not in _VALID_ACTIONS:
        raise ValueError(f"invalid action: {action}")
    return DedupAuditEvent(
        namespace=namespace,
        incoming_content_hash=incoming_content_hash,
        reviewed_memory_id=reviewed_memory_id,
        similarity=similarity,
        verdict=verdict,
        action=action,
        reason=reason,
        merge_target_file=merge_target_file,
        created_at=datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
    )


def append_dedup_audit_event(log_file: str | Path, event: DedupAuditEvent) -> None:
    path = Path(log_file)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(asdict(event), ensure_ascii=False) + "\n")
