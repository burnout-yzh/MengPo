"""Freshness scoring (T3): WangYou_Decay baseline.

Semantic relevance remains the primary ranking signal. This module provides
the secondary freshness score used only for re-ranking semantic candidates.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
UTC = timezone.utc
from math import exp


def _ensure_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


@dataclass(frozen=True)
class FreshnessParams:
    """Configurable time-decay parameters.

    ``initial_strength``:
        The baseline memory strength right after effective recall.
    ``half_life_days``:
        Effective half-life in days (= :yaml:`decay.tau` in bowl.yaml).
    ``shrink_factor``:
        Global multiplier to tighten/loosen freshness impact.
        This is **not** the S3 shrink factor — S3 lives in
        ``Sansheng_Stone`` and reads :yaml:`sansheng_stone.shrink_factor`.
    ``floor``:
        Lower bound to avoid exact zero when very old.
    """

    initial_strength: float = 1.0
    half_life_days: float = 7.0
    shrink_factor: float = 1.0
    floor: float = 0.01

    @classmethod
    def from_config(cls, decay_cfg=None):
        """Create FreshnessParams from :yaml:`decay.*` in bowl.yaml.

        Parameters
        ----------
        decay_cfg:
            A ``DecayConfig`` object, or ``None`` to auto-load from config.
        """
        if decay_cfg is None:
            from .config import Config
            decay_cfg = Config.load_cached().decay
        return cls(
            initial_strength=decay_cfg.initial_strength,
            half_life_days=decay_cfg.tau,
            shrink_factor=1.0,
            floor=decay_cfg.floor,
        )


def WangYou_Decay(
    *,
    now: datetime,
    last_effective_recall_at: datetime,
    params: FreshnessParams | None = None,
) -> float:
    """Compute normalized freshness score in [floor, initial_strength]."""
    if params is None:
        params = FreshnessParams.from_config()
    now_utc = _ensure_utc(now)
    recall_utc = _ensure_utc(last_effective_recall_at)
    delta_days = max(0.0, (now_utc - recall_utc).total_seconds() / 86400.0)

    if params.half_life_days <= 0:
        raise ValueError("half_life_days must be > 0")
    if not (0.0 <= params.floor <= params.initial_strength):
        raise ValueError("floor must be in [0, initial_strength]")
    if params.shrink_factor <= 0:
        raise ValueError("shrink_factor must be > 0")

    decay_lambda = 0.6931471805599453 / params.half_life_days
    raw = params.initial_strength * exp(-decay_lambda * delta_days)
    shrunk = raw * params.shrink_factor
    return max(params.floor, min(params.initial_strength, shrunk))


# Backward-compatible alias.
freshness_score = WangYou_Decay
