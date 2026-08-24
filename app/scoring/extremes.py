"""Flags an indicator as at/near a new high or low since the last major recession.

"Since the last major recession" is derived from the seeded crisis-event list (the most
recent recession_start date) rather than a hardcoded date, so it stays correct as new events
are added to seed/events.py over time.
"""

from __future__ import annotations

from datetime import date

from app.seed.events import CRISIS_EVENTS

NEAR_BAND_FRACTION = 0.05  # within 5% of the observed range counts as "near"

_recession_starts = [e["recession_start"] for e in CRISIS_EVENTS if e["recession_start"] is not None]
LAST_RECESSION_START: date = max(_recession_starts)

# kind is a stable, language-agnostic identifier - the caller (API route/frontend) composes
# the localized sentence ("New High since Feb 2020" / "自2020年2月以来新高") from kind + the
# since-date, so this module never needs to know what language it's being displayed in.
ExtremeKind = str  # "new_high" | "near_high" | "new_low" | "near_low"


def extreme_flag(current: float, hist_min: float, hist_max: float, polarity: str) -> tuple[ExtremeKind | None, str | None]:
    """Returns (kind, tone), or (None, None) if the current value isn't near either edge of
    its since-last-recession range.

    tone is polarity-aware: a new high is "positive" for a higher-is-healthy indicator (e.g.
    breadth at its best since 2020) but "negative" for a lower-is-healthy one (e.g. VIX at its
    worst since 2020). Ambiguous ("custom") polarity indicators get a neutral tone - still
    worth flagging as unusual, without asserting whether it's good or bad.
    """
    rng = hist_max - hist_min
    if rng <= 0:
        return None, None
    band = rng * NEAR_BAND_FRACTION

    if current >= hist_max:
        kind, direction = "new_high", "high"
    elif current >= hist_max - band:
        kind, direction = "near_high", "high"
    elif current <= hist_min:
        kind, direction = "new_low", "low"
    elif current <= hist_min + band:
        kind, direction = "near_low", "low"
    else:
        return None, None

    if polarity == "higher_is_healthy":
        tone = "positive" if direction == "high" else "negative"
    elif polarity == "lower_is_healthy":
        tone = "negative" if direction == "high" else "positive"
    else:
        tone = "neutral"

    return kind, tone
