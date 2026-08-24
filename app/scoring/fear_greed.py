"""Proprietary Market Fear/Greed Index (PRD Section 12).

Built dashboard-native from existing indicator scores rather than a third-party sentiment
score. Output is 0-100: 0 = extreme fear/stress, 100 = extreme greed/risk appetite -
deliberately a different axis than the 0-100 "health" score, since "healthy" and "greedy"
sometimes point in different directions (see margin debt below).

Section 12 suggests: VIX percentile, equity put/call percentile, breadth, HY credit spread
percentile, S&P momentum, HYG/LQD relative strength, margin debt growth, new highs/lows,
small-cap relative strength, defensive/cyclical relative strength. This build uses every one
of those with a seeded indicator (all but defensive/cyclical relative strength, which isn't
in the current registry) - see the seed file to add more components later.

For most components, a high health_score (calm/orderly conditions) IS the greedy direction:
low VIX, tight credit spreads, strong breadth are all simultaneously "healthy" and "greedy".
Margin debt is the exception - rising leverage is MORE greed (risk appetite) but is scored
lower_is_healthy (more fragile), so its contribution is inverted.
"""

from __future__ import annotations

from app.scoring.aggregate import ScoredIndicator

# slug -> invert (True means greed = 100 - health_score, i.e. use the raw stress percentile
# direction instead of the health direction)
COMPONENT_SLUGS: dict[str, bool] = {
    "vix": False,
    "equity-put-call": False,
    "pct-above-200dma": False,
    "hy-oas": False,
    "spx-level": False,  # momentum/level proxy - no separate momentum series in this build
    "hyg-lqd-rel": False,
    "margin-debt-mktcap": True,  # rising leverage = more greed, but scored lower_is_healthy
    "new-highs-minus-lows": False,
    "russell-vs-sp500": False,  # small-cap relative strength
}


def compute_fear_greed_index(scored_by_slug: dict[str, ScoredIndicator]) -> float | None:
    values: list[float] = []
    for slug, invert in COMPONENT_SLUGS.items():
        s = scored_by_slug.get(slug)
        if s is None or s.is_stale:
            continue
        values.append(100 - s.health_score if invert else s.health_score)

    if len(values) < 4:  # not enough live components for a meaningful composite
        return None
    return round(sum(values) / len(values), 1)


def fear_greed_label(value: float) -> str:
    if value >= 80:
        return "Extreme Greed"
    if value >= 60:
        return "Greed"
    if value >= 40:
        return "Neutral"
    if value >= 20:
        return "Fear"
    return "Extreme Fear"
