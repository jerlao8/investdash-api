"""Raw normalization (PRD Section 5.1): percentiles, robust z-scores, rate-of-change z-scores."""

from __future__ import annotations

import statistics
from dataclasses import dataclass


def percentile_rank(current: float, history: list[float]) -> float:
    """% of historical values <= current. Empty/singleton history -> 50 (neutral)."""
    if len(history) < 2:
        return 50.0
    below = sum(1 for v in history if v <= current)
    return 100.0 * below / len(history)


def robust_z_score(current: float, history: list[float]) -> float:
    """Median/MAD-based z-score - resistant to outliers/regime shifts vs a plain mean/stdev z."""
    if len(history) < 2:
        return 0.0
    median = statistics.median(history)
    abs_devs = [abs(v - median) for v in history]
    mad = statistics.median(abs_devs)
    if mad == 0:
        return 0.0
    return 0.6745 * (current - median) / mad


def rate_of_change_series(values: list[float]) -> list[float]:
    return [values[i] - values[i - 1] for i in range(1, len(values))]


@dataclass
class NormalizationResult:
    percentile_5y: float
    percentile_10y: float
    percentile_full: float
    z_score: float
    velocity_z_score: float


def normalize(
    current: float,
    history_5y: list[float],
    history_10y: list[float],
    history_full: list[float],
) -> NormalizationResult:
    roc_full = rate_of_change_series(history_full) if len(history_full) > 1 else []
    current_roc = history_full[-1] - history_full[-2] if len(history_full) > 1 else 0.0
    return NormalizationResult(
        percentile_5y=percentile_rank(current, history_5y),
        percentile_10y=percentile_rank(current, history_10y),
        percentile_full=percentile_rank(current, history_full),
        z_score=robust_z_score(current, history_full),
        velocity_z_score=robust_z_score(current_roc, roc_full) if roc_full else 0.0,
    )
