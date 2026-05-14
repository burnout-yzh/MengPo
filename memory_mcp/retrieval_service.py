"""End-to-end retrieval service facade over retrieval_flow."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .database import Database
from .retrieval import RetrievalCandidate, SessionDeliveryState
from .retrieval_flow import RetrievalFlowResult, run_retrieval_round


@dataclass
class RetrievalService:
    db: Database
    telemetry_log_file: str | Path
    enable_duoshe: bool = False
    duoshe_root: str | Path = "memory_test_files"

    def __post_init__(self) -> None:
        self._session_state = SessionDeliveryState()
        self._duoshe_injected_sessions: set[str] = set()

    def _load_duoshe_prompts(self) -> tuple[str, ...]:
        root = Path(self.duoshe_root)
        names = ("AGENTS.md", "MEMORY.md", "PROFILE.md", "SOUL.md")
        prompts: list[str] = []
        for name in names:
            path = root / name
            if path.exists():
                prompts.append(path.read_text(encoding="utf-8"))
        return tuple(prompts)

    def run_round(
        self,
        *,
        session_id: str,
        query: str,
        namespace: str,
        candidates: list[RetrievalCandidate],
        s2_effectiveness_map: dict[str, int] | None,
        expand: bool,
        shrink_factor: float = 0.25,
    ) -> RetrievalFlowResult:
        result = run_retrieval_round(
            db=self.db,
            session_state=self._session_state,
            session_id=session_id,
            query=query,
            namespace=namespace,
            candidates=candidates,
            s2_effectiveness_map=s2_effectiveness_map,
            telemetry_log_file=self.telemetry_log_file,
            expand=expand,
            shrink_factor=shrink_factor,
        )
        if not self.enable_duoshe:
            return result
        if session_id in self._duoshe_injected_sessions:
            return result
        self._duoshe_injected_sessions.add(session_id)
        return RetrievalFlowResult(
            delivered_ids=result.delivered_ids,
            effective_ids=result.effective_ids,
            writeback_count=result.writeback_count,
            all_invalid=result.all_invalid,
            duoshe_prompts=self._load_duoshe_prompts(),
        )

    def reset_session(self, session_id: str) -> None:
        self._session_state.clear_session(session_id)
        self._duoshe_injected_sessions.discard(session_id)
