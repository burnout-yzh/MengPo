"""Retrieval telemetry schema and logging helpers (T5)."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
UTC = timezone.utc
from pathlib import Path


@dataclass(frozen=True)
class RetrievalEvent:
    query: str
    namespace: str
    memory_id: int
    semantic_score: float
    WangYou_Decay: float
    rank_before: int
    rank_after: int
    s2_effective: bool
    s3_written_back: bool
    created_at: str


@dataclass(frozen=True)
class RetrievalRoundEvent:
    session_id: str
    query: str
    namespace: str
    delivered_count: int
    effective_count: int
    writeback_count: int
    all_invalid: bool
    protocol_valid: bool
    protocol_error_code: str | None
    expand: bool
    created_at: str


def make_event(
    *,
    query: str,
    namespace: str,
    memory_id: int,
    semantic_score: float,
    WangYou_Decay: float,
    rank_before: int,
    rank_after: int,
    s2_effective: bool,
    s3_written_back: bool,
) -> RetrievalEvent:
    return RetrievalEvent(
        query=query,
        namespace=namespace,
        memory_id=memory_id,
        semantic_score=semantic_score,
        WangYou_Decay=WangYou_Decay,
        rank_before=rank_before,
        rank_after=rank_after,
        s2_effective=s2_effective,
        s3_written_back=s3_written_back,
        created_at=datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
    )


def append_event(log_file: str | Path, event: RetrievalEvent) -> None:
    path = Path(log_file)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = asdict(event)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")


def make_round_event(
    *,
    session_id: str,
    query: str,
    namespace: str,
    delivered_count: int,
    effective_count: int,
    writeback_count: int,
    all_invalid: bool,
    protocol_valid: bool,
    protocol_error_code: str | None,
    expand: bool,
) -> RetrievalRoundEvent:
    return RetrievalRoundEvent(
        session_id=session_id,
        query=query,
        namespace=namespace,
        delivered_count=delivered_count,
        effective_count=effective_count,
        writeback_count=writeback_count,
        all_invalid=all_invalid,
        protocol_valid=protocol_valid,
        protocol_error_code=protocol_error_code,
        expand=expand,
        created_at=datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
    )


def append_round_event(log_file: str | Path, event: RetrievalRoundEvent) -> None:
    path = Path(log_file)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = asdict(event)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")
