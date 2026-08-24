"""One-time historical MarketSnapshot reconstruction.

The live/mock pipeline only ever writes a MarketSnapshot for "today" - a fresh deployment
therefore has no history to compare against for a "how has this changed vs. a week/month/
quarter/year ago" summary (Daily Feed Section 30's spirit, extended). But indicator
*observations* are already backfilled 12 years deep (Section 5's historical scoring engine
needs that depth for percentiles anyway), so this reuses the exact same scoring/aggregate
code path, just re-run at each historical as_of date against the observation history
truncated to that date - rather than a separate approximation.

This does not persist per-indicator IndicatorScore rows for backfilled dates (that would be
~107 indicators x ~90 dates of extra rows for no current use) - only the aggregate
MarketSnapshot, which is all the daily-summary feature needs.
"""

from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import IndicatorDefinition, IndicatorObservation, MarketSnapshot
from app.scoring.aggregate import ScoredIndicator, compute_corroboration, compute_factor_scores, finalize_scores
from app.scoring.fear_greed import compute_fear_greed_index
from app.scoring.health_score import compute_components

# Daily for the last 35 days (accurate week/month lookback + a usable sparkline), weekly out
# to `days`, plus the exact quarter/year anchors guaranteed even if the weekly stride skips them.
def _backfill_dates(days: int) -> list[date]:
    today = date.today()
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
    definitions = db.query(IndicatorDefinition).filter(IndicatorDefinition.active == True).all()  # noqa: E712
    if not definitions:
        return 0

    history_by_id: dict[int, list[tuple[date, float]]] = {}
    for defn in definitions:
        rows = (
            db.query(IndicatorObservation.observation_date, IndicatorObservation.value)
            .filter(IndicatorObservation.indicator_id == defn.id)
            .order_by(IndicatorObservation.observation_date.asc())
            .all()
        )
        history_by_id[defn.id] = list(rows)

    existing_dates = {d for (d,) in db.query(MarketSnapshot.snapshot_date).all()}
    target_dates = [d for d in _backfill_dates(days) if d not in existing_dates]

    created = 0
    for as_of in target_dates:
        scored_list: list[ScoredIndicator] = []
        for defn in definitions:
            upto = [(d, v) for d, v in history_by_id[defn.id] if d <= as_of]
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
                    slug=defn.slug, cluster=defn.cluster, category=defn.category, components=components,
                    green_threshold=defn.green_threshold, yellow_threshold=defn.yellow_threshold,
                    is_stale=False, indicator_id=defn.id,
                )
            )

        if not scored_list:
            continue

        compute_corroboration(scored_list)
        finalize_scores(scored_list)
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
