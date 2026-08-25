"""Point-in-time score reconstruction from observation history.

The live/mock pipeline only ever writes a MarketSnapshot for "today" (plus a short recent
backfill). For historical crisis windows we re-run the same scoring/aggregate path against
observations truncated to each as_of date — not true vintage/ALFRED reconstruction, but the
dashboard's applied U.S. Equity Health algorithm as of that day.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import IndicatorDefinition, IndicatorObservation, MarketSnapshot
from app.scoring.aggregate import (
    FactorScores,
    ScoredIndicator,
    compute_corroboration,
    compute_factor_scores,
    finalize_scores,
)
from app.scoring.fear_greed import compute_fear_greed_index
from app.scoring.health_score import compute_components
from app.timeutil import today_pt

HistoryById = dict[int, list[tuple[date, float]]]


def load_observation_history(db: Session, definitions: list[IndicatorDefinition] | None = None) -> tuple[list[IndicatorDefinition], HistoryById]:
    if definitions is None:
        definitions = db.query(IndicatorDefinition).filter(IndicatorDefinition.active == True).all()  # noqa: E712
    history_by_id: HistoryById = {}
    for defn in definitions:
        rows = (
            db.query(IndicatorObservation.observation_date, IndicatorObservation.value)
            .filter(IndicatorObservation.indicator_id == defn.id)
            .order_by(IndicatorObservation.observation_date.asc())
            .all()
        )
        history_by_id[defn.id] = list(rows)
    return definitions, history_by_id


def reconstruct_scored_as_of(
    definitions: list[IndicatorDefinition],
    history_by_id: HistoryById,
    as_of: date,
) -> list[ScoredIndicator]:
    """Apply today's scoring algorithm to observation history available on `as_of`."""
    scored_list: list[ScoredIndicator] = []
    for defn in definitions:
        upto = [(d, v) for d, v in history_by_id.get(defn.id, []) if d <= as_of]
        if len(upto) < 2:
            continue
        values_full = [v for _, v in upto]
        cutoff_5y = as_of - timedelta(days=365 * 5)
        cutoff_10y = as_of - timedelta(days=365 * 10)
        values_5y = [v for d, v in upto if d >= cutoff_5y] or values_full
        values_10y = [v for d, v in upto if d >= cutoff_10y] or values_full
        current = values_full[-1]

        components = compute_components(defn.slug, current, values_5y, values_10y, values_full, defn.health_polarity)
        scored_list.append(
            ScoredIndicator(
                slug=defn.slug,
                cluster=defn.cluster,
                category=defn.category,
                components=components,
                green_threshold=defn.green_threshold,
                yellow_threshold=defn.yellow_threshold,
                is_stale=False,
                indicator_id=defn.id,
            )
        )

    if not scored_list:
        return []

    compute_corroboration(scored_list)
    finalize_scores(scored_list)
    return scored_list


def reconstruct_factor_scores_as_of(
    definitions: list[IndicatorDefinition],
    history_by_id: HistoryById,
    as_of: date,
) -> FactorScores | None:
    scored_list = reconstruct_scored_as_of(definitions, history_by_id, as_of)
    if not scored_list:
        return None
    return compute_factor_scores(scored_list)


def us_equity_health_as_of(
    definitions: list[IndicatorDefinition],
    history_by_id: HistoryById,
    as_of: date,
) -> dict[str, Any] | None:
    scored_list = reconstruct_scored_as_of(definitions, history_by_id, as_of)
    if not scored_list:
        return None
    factors = compute_factor_scores(scored_list)
    return {
        "as_of": as_of.isoformat(),
        "us_equity_score": factors.overall_0_10,
        "overall_status": factors.overall_status,
    }


def reconstruct_score_series(
    definitions: list[IndicatorDefinition],
    history_by_id: HistoryById,
    start: date,
    end: date,
    step_days: int = 7,
) -> list[dict[str, Any]]:
    """Weekly (by default) reconstructed U.S. Equity Health points across [start, end]."""
    if end < start:
        start, end = end, start
    dates: list[date] = []
    d = start
    while d <= end:
        dates.append(d)
        d += timedelta(days=step_days)
    if not dates or dates[-1] != end:
        dates.append(end)

    out: list[dict[str, Any]] = []
    for as_of in dates:
        point = us_equity_health_as_of(definitions, history_by_id, as_of)
        if point is None:
            continue
        out.append(
            {
                "date": point["as_of"],
                "us_equity_score": point["us_equity_score"],
                "overall_status": point["overall_status"],
            }
        )
    return out


# Daily for the last 35 days (accurate week/month lookback + a usable sparkline), weekly out
# to `days`, plus the exact quarter/year anchors guaranteed even if the weekly stride skips them.
def _backfill_dates(days: int) -> list[date]:
    today = today_pt()
    dates: set[date] = set()
    for i in range(0, 36):
        dates.add(today - timedelta(days=i))
    for i in range(35, days + 1, 7):
        dates.add(today - timedelta(days=i))
    for anchor in (7, 30, 91, 365):
        dates.add(today - timedelta(days=anchor))
    return sorted(d for d in dates if d <= today)


def backfill_market_snapshots(db: Session, days: int = 400, min_existing: int = 40) -> int:
    if db.query(MarketSnapshot).count() > min_existing:
        return 0

    settings = get_settings()
    definitions, history_by_id = load_observation_history(db)
    if not definitions:
        return 0

    existing_dates = {d for (d,) in db.query(MarketSnapshot.snapshot_date).all()}
    target_dates = [d for d in _backfill_dates(days) if d not in existing_dates]

    created = 0
    for as_of in target_dates:
        scored_list = reconstruct_scored_as_of(definitions, history_by_id, as_of)
        if not scored_list:
            continue

        factor_scores = compute_factor_scores(scored_list)
        fear_greed = compute_fear_greed_index({s.slug: s for s in scored_list})

        db.add(
            MarketSnapshot(
                snapshot_date=as_of,
                us_equity_score=factor_scores.overall_0_10,
                us_macro_score=factor_scores.scores_0_10.get("us_macro", 5.0),
                global_score=factor_scores.scores_0_10.get("global_spillover", 5.0),
                liquidity_score=factor_scores.scores_0_10.get("liquidity", 5.0),
                credit_score=factor_scores.scores_0_10.get("credit_funding", 5.0),
                ai_funding_score=factor_scores.ai_funding_0_10,
                valuation_score=factor_scores.scores_0_10.get("valuation_positioning", 5.0),
                equity_internals_score=factor_scores.scores_0_10.get("equity_internals", 5.0),
                fear_greed_index=fear_greed,
                overall_status=factor_scores.overall_status,
                algorithm_version=f"{settings.algorithm_version}-backfill",
            )
        )
        created += 1

    if created:
        db.commit()
    return created
