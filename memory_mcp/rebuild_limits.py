"""T15 precheck limits for markdown rebuild scans.

`-1` means unlimited for each bound.
"""

from __future__ import annotations

from dataclasses import dataclass


DEFAULT_WARN_MAX_FILES = 250_000  # WARNING_CHUNKS ~ 250k
DEFAULT_HARD_MAX_FILES = 500_000  # MAX_CHUNKS ~ 500k
DEFAULT_WARN_MAX_BYTES = 25 * 1024 * 1024 * 1024  # ~25 GiB @ 250k chunks
DEFAULT_HARD_MAX_BYTES = 50 * 1024 * 1024 * 1024  # ~50 GiB @ 500k chunks


@dataclass(frozen=True)
class RebuildScanLimits:
    warn_max_files: int = DEFAULT_WARN_MAX_FILES
    hard_max_files: int = DEFAULT_HARD_MAX_FILES
    warn_max_bytes: int = DEFAULT_WARN_MAX_BYTES
    hard_max_bytes: int = DEFAULT_HARD_MAX_BYTES


@dataclass(frozen=True)
class RebuildScanStats:
    total_files: int
    total_bytes: int


@dataclass(frozen=True)
class RebuildPrecheckResult:
    warn: bool
    blocked: bool
    reason: str | None


def evaluate_rebuild_limits(stats: RebuildScanStats, limits: RebuildScanLimits) -> RebuildPrecheckResult:
    """Evaluate scan stats against warn/hard bounds.

    For any limit field, `-1` means unlimited.
    """

    hard_files_hit = _is_hit(stats.total_files, limits.hard_max_files)
    hard_bytes_hit = _is_hit(stats.total_bytes, limits.hard_max_bytes)
    if hard_files_hit or hard_bytes_hit:
        reasons: list[str] = []
        if hard_files_hit:
            reasons.append("hard_max_files")
        if hard_bytes_hit:
            reasons.append("hard_max_bytes")
        return RebuildPrecheckResult(warn=False, blocked=True, reason=",".join(reasons))

    warn = _is_hit(stats.total_files, limits.warn_max_files) or _is_hit(stats.total_bytes, limits.warn_max_bytes)
    return RebuildPrecheckResult(warn=warn, blocked=False, reason=None)


def _is_hit(actual: int, limit: int) -> bool:
    if limit == -1:
        return False
    if limit < -1:
        raise ValueError("limit must be -1 (unlimited) or >= 0")
    return actual > limit
