"""Deterministic synthetic time-series generator backing every mock connector.

Given the same slug + params, always produces the same history (seeded RNG keyed off the
slug) so re-running the seed script is idempotent. Used so we can demo the full pipeline
(ingest -> normalize -> score -> aggregate -> alert) with realistic-looking data for ~110
indicators without hand-authoring hundreds of fixture files.

Critical: the walk is anchored at a FIXED origin date. Sliding `start`/`end` together (as
connectors do with end=today, start=today-12y) must not preserve path length — that bug made
every newly inserted "today" point reuse the same terminal RNG value, so 1D changes were
always zero and Worst/Best movers stayed empty.
"""

from __future__ import annotations

import hashlib
import math
import random
from dataclasses import dataclass
from datetime import date, timedelta

FREQ_STEP_DAYS = {"daily": 1, "weekly": 7, "monthly": 30, "quarterly": 91, "annual": 365}

# Fixed calendar origin for the RNG walk. Values at each stepped date are stable forever;
# extending `end` appends new shocks instead of sliding the window.
_WALK_ORIGIN = date(2000, 1, 1)


def normalize_frequency(frequency: str | None) -> str:
    """Map indicator frequency labels onto the synthetic generator's supported steps."""
    if not frequency:
        return "daily"
    key = frequency.strip().lower()
    return key if key in FREQ_STEP_DAYS else "daily"


@dataclass
class MockParams:
    base: float
    vol: float  # stdev of each step, in value units
    drift: float = 0.0  # long-run per-step drift
    floor: float | None = None
    ceiling: float | None = None
    cycle_amplitude: float = 0.0  # adds a slow sine cycle to mimic macro regimes
    cycle_period_days: int = 900
    mean_reversion: float = 0.02  # pulls value back toward base each step


def _seed_for(slug: str) -> int:
    return int(hashlib.sha256(slug.encode()).hexdigest()[:8], 16)


def _clamp(v: float, params: MockParams) -> float:
    if params.floor is not None:
        v = max(v, params.floor)
    if params.ceiling is not None:
        v = min(v, params.ceiling)
    return v


def backfill_series(
    slug: str, frequency: str, params: MockParams, start: date, end: date
) -> list[tuple[date, float]]:
    if end < start:
        start, end = end, start

    rng = random.Random(_seed_for(slug))
    freq = normalize_frequency(frequency)
    step_days = FREQ_STEP_DAYS[freq]
    points: list[tuple[date, float]] = []
    value = params.base
    d = _WALK_ORIGIN
    t = 0
    while d <= end:
        cycle = params.cycle_amplitude * math.sin(2 * math.pi * t * step_days / params.cycle_period_days)
        reversion = (params.base + cycle - value) * params.mean_reversion
        shock = rng.gauss(0, params.vol)
        value = value + reversion + params.drift + shock
        value = _clamp(value, params)
        if d >= start:
            points.append((d, round(value, 4)))
        d = d + timedelta(days=step_days)
        t += 1
    return points


def next_value(slug: str, last_value: float, params: MockParams, as_of: date) -> tuple[date, float]:
    rng = random.Random(_seed_for(slug) ^ as_of.toordinal())
    reversion = (params.base - last_value) * params.mean_reversion
    shock = rng.gauss(0, params.vol)
    value = _clamp(last_value + reversion + params.drift + shock, params)
    return as_of, round(value, 4)
