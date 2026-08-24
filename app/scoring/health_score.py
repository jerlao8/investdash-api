"""Indicator-level 0-100 health score (PRD Section 5.2/5.3).

health = 0.50*level + 0.25*velocity + 0.15*persistence + 0.10*cross_asset(corroboration)

`level`/`velocity`/`persistence` are computable from one indicator's own history.
`corroboration` needs visibility into sibling indicators in the same cluster, so it is
computed separately in aggregate.py (two-pass: compute per-indicator components first,
then corroboration across the cluster, then finalize).
"""

from __future__ import annotations

from dataclasses import dataclass

from app.scoring.normalize import normalize, percentile_rank, rate_of_change_series

WEIGHTS = {"level": 0.50, "velocity": 0.25, "persistence": 0.15, "cross_asset": 0.10}

# Non-monotonic indicators (Section 15: inflation isn't simply "bad if high") register a
# custom oriented-percentile function here instead of the default polarity mapping.
CUSTOM_POLARITY_FNS: dict[str, callable] = {}


@dataclass
class ScoreComponents:
    level: float
    velocity: float
    persistence: float
    z_score: float
    percentile_full: float
    direction: str  # positive|negative|flat - polarity-oriented ("is this healthier?"), drives COLOR
    raw_trend: str = "flat"  # up|down|flat - literal value movement, polarity-independent, drives ARROW SHAPE


def _oriented(value: float, polarity: str) -> float:
    """Flip sign so 'higher is always healthier' regardless of raw polarity."""
    return value if polarity == "higher_is_healthy" else -value


def compute_components(
    slug: str,
    current: float,
    history_5y: list[float],
    history_10y: list[float],
    history_full: list[float],
    polarity: str,
    persistence_window: int = 10,
) -> ScoreComponents:
    custom_fn = CUSTOM_POLARITY_FNS.get(slug)
    norm = normalize(current, history_5y, history_10y, history_full)

    if custom_fn is not None:
        level = custom_fn(current, history_full)
    else:
        level = norm.percentile_full if polarity == "higher_is_healthy" else 100 - norm.percentile_full

    # Velocity: percentile-rank the *oriented* rate of change, so an improving move scores high.
    if len(history_full) > 2:
        roc = rate_of_change_series(history_full)
        oriented_roc = [_oriented(r, polarity) for r in roc]
        current_oriented_roc = _oriented(history_full[-1] - history_full[-2], polarity)
        velocity = percentile_rank(current_oriented_roc, oriented_roc)
    else:
        velocity = 50.0

    # Persistence: how many of the most recent steps were adverse in a row -> penalize.
    persistence = 100.0
    if len(history_full) > 2:
        roc = rate_of_change_series(history_full)
        oriented_roc = [_oriented(r, polarity) for r in roc]
        window = oriented_roc[-persistence_window:]
        streak = 0
        for r in reversed(window):
            if r < 0:
                streak += 1
            else:
                break
        persistence = 100.0 * (1 - streak / max(len(window), 1))

    direction = "flat"
    raw_trend = "flat"
    if len(history_full) > 1:
        raw_change = history_full[-1] - history_full[-2]
        oriented_change = _oriented(raw_change, polarity)
        direction = "positive" if oriented_change > 0 else ("negative" if oriented_change < 0 else "flat")
        raw_trend = "up" if raw_change > 0 else ("down" if raw_change < 0 else "flat")

    return ScoreComponents(
        level=level,
        velocity=velocity,
        persistence=persistence,
        z_score=norm.z_score,
        percentile_full=norm.percentile_full,
        direction=direction,
        raw_trend=raw_trend,
    )


def finalize_health_score(level: float, velocity: float, persistence: float, corroboration: float) -> float:
    score = (
        WEIGHTS["level"] * level
        + WEIGHTS["velocity"] * velocity
        + WEIGHTS["persistence"] * persistence
        + WEIGHTS["cross_asset"] * corroboration
    )
    return max(0.0, min(100.0, score))


def color_state(score: float, green_threshold: float = 70.0, yellow_threshold: float = 40.0) -> str:
    if score >= green_threshold:
        return "green"
    if score >= yellow_threshold:
        return "yellow"
    return "red"


# Fallback-only generic copy (PRD Section 3: "whether high or low is healthy" is a required
# popover field). Every seeded indicator carries its own specific reading_guide text in
# seed/indicators.py - a generic per-polarity template reads as boilerplate once you've seen
# it on a few cards. This is used only if an indicator's own guide field is left blank.
def reading_guide(polarity: str, lang: str = "en") -> str:
    if lang == "zh":
        if polarity == "higher_is_healthy":
            return "数值越高越健康。箭头直接跟踪原始数值走势：▲表示上升（利好），▼表示下降（利空）。"
        if polarity == "lower_is_healthy":
            return "数值越低越健康。箭头反映的是整体健康状况，而非原始数值本身：▲表示状况改善（数值很可能下降），▼表示状况恶化（数值很可能上升）。"
        return "该指标与健康状况并非单调对应关系 - 请参见上方说明了解具体解读方式。箭头反映的是仪表盘对最新变动是利好（▲）还是利空（▼）美股的当前判断。"

    if polarity == "higher_is_healthy":
        return (
            "Higher values are healthier here. The arrow tracks the raw value directly: "
            "▲ means it rose (favorable), ▼ means it fell (unfavorable)."
        )
    if polarity == "lower_is_healthy":
        return (
            "Lower values are healthier here. The arrow tracks overall health, not the raw "
            "number: ▲ means conditions improved (the value likely fell), ▼ means conditions "
            "worsened (the value likely rose)."
        )
    return (
        "This indicator doesn't move monotonically with health - see the description above "
        "for how to interpret it. The arrow reflects the dashboard's current read on whether "
        "the latest move was favorable (▲) or unfavorable (▼) for equities."
    )
