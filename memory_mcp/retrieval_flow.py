"""T7/T8/T10 retrieval flow orchestration helpers.

This module wires ranking/protocol validation/write-back/round telemetry with
the existing policy helpers, while keeping semantic retrieval itself external.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
UTC = timezone.utc
from pathlib import Path

from .database import Database
from .retrieval import (
    RetrievalCandidate,
    RetrievalProtocolError,
    SessionDeliveryState,
    process_retrieval_round,
)
from .telemetry import append_round_event, make_round_event


def _append_round_event_best_effort(telemetry_log_file: str | Path, event: dict[str, object]) -> None:
    try:
        append_round_event(telemetry_log_file, event)
    except Exception as exc:
        logging.warning("telemetry append failed: %s", exc)


@dataclass(frozen=True)
class RetrievalFlowResult:
    delivered_ids: tuple[int, ...]
    effective_ids: tuple[int, ...]
    writeback_count: int
    all_invalid: bool
    duoshe_prompts: tuple[str, ...] = ()


def run_retrieval_round(
    *,
    db: Database,
    session_state: SessionDeliveryState,
    session_id: str,
    query: str,
    namespace: str,
    candidates: list[RetrievalCandidate],
    s2_effectiveness_map: dict[str, int] | None,
    telemetry_log_file: str | Path,
    expand: bool,
    shrink_factor: float = 0.25,
) -> RetrievalFlowResult:
    """Run one round with strict protocol handling.

    Protocol errors are logged and re-raised as round-failure signals.
    """
    excluded = session_state.excluded_ids(session_id) if expand else set()
    try:
        outcome = process_retrieval_round(
            candidates,
            s2_effectiveness_map=s2_effectiveness_map,
            excluded_memory_ids=excluded,
        )
    except RetrievalProtocolError as exc:
        _append_round_event_best_effort(
            telemetry_log_file,
            make_round_event(
                session_id=session_id,
                query=query,
                namespace=namespace,
                delivered_count=0,
                effective_count=0,
                writeback_count=0,
                all_invalid=False,
                protocol_valid=False,
                protocol_error_code=exc.code.value,
                expand=expand,
            ),
        )
        raise

    delivered_ids = outcome.delivered.delivered_ids
    writeback_count = 0
    effective_ids: tuple[int, ...] = ()
    all_invalid = False

    if outcome.writeback_plan is not None:
        effective_ids = outcome.writeback_plan.effective_ids
        all_invalid = outcome.writeback_plan.all_invalid
        if effective_ids:
            writeback_count = db.Sansheng_Stone(
                memory_ids=list(effective_ids),
                shrink_factor=shrink_factor,
                now=datetime.now(UTC),
            )

    session_state.record_judged_ids(session_id, list(delivered_ids))
    _append_round_event_best_effort(
        telemetry_log_file,
        make_round_event(
            session_id=session_id,
            query=query,
            namespace=namespace,
            delivered_count=len(delivered_ids),
            effective_count=len(effective_ids),
            writeback_count=writeback_count,
            all_invalid=all_invalid,
            protocol_valid=True,
            protocol_error_code=None,
            expand=expand,
        ),
    )

    return RetrievalFlowResult(
        delivered_ids=delivered_ids,
        effective_ids=effective_ids,
        writeback_count=writeback_count,
        all_invalid=all_invalid,
    )
