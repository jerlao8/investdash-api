from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import get_latest_scores
from app.db.models import AlertEvent, MarketSnapshot
from app.db.session import get_db
from app.schemas.responses import HealthOverview

router = APIRouter()


@router.get("/health/overview", response_model=HealthOverview)
def health_overview(db: Session = Depends(get_db)) -> HealthOverview:
    latest_snap = db.query(MarketSnapshot).order_by(MarketSnapshot.snapshot_date.desc()).first()
    if latest_snap is None:
        return HealthOverview(
            snapshot_date=None, us_equity_score=5.0, us_macro_score=5.0, global_score=5.0, liquidity_score=5.0,
            credit_score=5.0, ai_funding_score=5.0, valuation_score=5.0, equity_internals_score=5.0,
            overall_status="Caution",
        )

    yesterday_snap = (
        db.query(MarketSnapshot)
        .filter(MarketSnapshot.snapshot_date < latest_snap.snapshot_date)
        .order_by(MarketSnapshot.snapshot_date.desc())
        .first()
    )
    month_cutoff = latest_snap.snapshot_date - timedelta(days=30)
    month_snap = (
        db.query(MarketSnapshot)
        .filter(MarketSnapshot.snapshot_date <= month_cutoff)
        .order_by(MarketSnapshot.snapshot_date.desc())
        .first()
    )
    sparkline_rows = (
        db.query(MarketSnapshot)
        .filter(MarketSnapshot.snapshot_date >= latest_snap.snapshot_date - timedelta(days=90))
        .order_by(MarketSnapshot.snapshot_date.asc())
        .all()
    )

    scores = get_latest_scores(db)
    stale = sum(1 for s in scores.values() if s.color_state == "gray")
    green = sum(1 for s in scores.values() if s.color_state == "green")
    yellow = sum(1 for s in scores.values() if s.color_state == "yellow")
    red = sum(1 for s in scores.values() if s.color_state == "red")

    today_alerts = db.query(AlertEvent).filter(func.date(AlertEvent.timestamp) == latest_snap.snapshot_date).all()
    emergency_count = sum(1 for a in today_alerts if a.severity == "emergency")
    warning_count = sum(1 for a in today_alerts if a.severity in ("warning", "red"))

    def _delta_1d(field: str) -> float | None:
        if yesterday_snap is None:
            return None
        return round(getattr(latest_snap, field) - getattr(yesterday_snap, field), 2)

    fear_greed_change_1d: float | None = None
    if yesterday_snap is not None and latest_snap.fear_greed_index is not None and yesterday_snap.fear_greed_index is not None:
        fear_greed_change_1d = round(latest_snap.fear_greed_index - yesterday_snap.fear_greed_index, 1)

    return HealthOverview(
        snapshot_date=latest_snap.snapshot_date,
        us_equity_score=latest_snap.us_equity_score,
        us_macro_score=latest_snap.us_macro_score,
        global_score=latest_snap.global_score,
        liquidity_score=latest_snap.liquidity_score,
        credit_score=latest_snap.credit_score,
        ai_funding_score=latest_snap.ai_funding_score,
        valuation_score=latest_snap.valuation_score,
        equity_internals_score=latest_snap.equity_internals_score,
        fear_greed_index=latest_snap.fear_greed_index,
        fear_greed_change_1d=fear_greed_change_1d,
        overall_status=latest_snap.overall_status,
        score_change_1d=round(latest_snap.us_equity_score - yesterday_snap.us_equity_score, 2) if yesterday_snap else None,
        score_change_1m=round(latest_snap.us_equity_score - month_snap.us_equity_score, 2) if month_snap else None,
        global_score_change_1d=_delta_1d("global_score"),
        liquidity_score_change_1d=_delta_1d("liquidity_score"),
        credit_score_change_1d=_delta_1d("credit_score"),
        us_macro_score_change_1d=_delta_1d("us_macro_score"),
        ai_funding_score_change_1d=_delta_1d("ai_funding_score"),
        sparkline_90d=[r.us_equity_score for r in sparkline_rows],
        last_refresh=datetime.utcnow(),
        stale_indicator_count=stale,
        emergency_count=emergency_count,
        warning_count=warning_count,
        green_count=green,
        yellow_count=yellow,
        red_count=red,
    )
