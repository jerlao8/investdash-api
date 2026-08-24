from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import get_lang, get_latest_scores
from app.db.models import AlertEvent, MarketSnapshot
from app.db.session import get_db
from app.schemas.responses import DailySummaryOut, PeriodComparisonOut, SummaryBlockOut
from app.scoring.daily_summary import generate_daily_summary

router = APIRouter()


@router.get("/daily-summary", response_model=DailySummaryOut)
def daily_summary(db: Session = Depends(get_db), lang: str = Depends(get_lang)) -> DailySummaryOut:
    current = db.query(MarketSnapshot).order_by(MarketSnapshot.snapshot_date.desc()).first()
    if current is None:
        raise HTTPException(status_code=404, detail="no market snapshot available yet")

    scores = get_latest_scores(db)
    red = sum(1 for s in scores.values() if s.color_state == "red")
    yellow = sum(1 for s in scores.values() if s.color_state == "yellow")
    green = sum(1 for s in scores.values() if s.color_state == "green")

    emergency_count = (
        db.query(AlertEvent)
        .filter(func.date(AlertEvent.timestamp) == current.snapshot_date, AlertEvent.severity == "emergency")
        .count()
    )

    headline, comparisons, blocks = generate_daily_summary(db, current, red, yellow, green, emergency_count, lang)

    return DailySummaryOut(
        generated_at=datetime.utcnow(),
        snapshot_date=current.snapshot_date,
        overall_score=current.us_equity_score,
        overall_status=current.overall_status,
        headline=headline,
        comparisons=[
            PeriodComparisonOut(label=c.label, lookback_date=c.lookback_date, deltas=c.deltas, pct_deltas=c.pct_deltas)
            for c in comparisons
        ],
        blocks=[SummaryBlockOut(title=b.title, tone=b.tone, sentences=b.sentences) for b in blocks],
    )
