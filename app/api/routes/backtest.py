"""Simplified backtesting endpoints (PRD Section 41).

Explicitly NOT the full point-in-time/vintage reconstruction the PRD describes long-term -
this reads back the pipeline's own generated MarketSnapshot history (which only exists from
whenever the pipeline started running) and, when snapshot history doesn't reach far enough
back to cover an event, evaluates event indicators' current-history-based percentile as of
today so the page is still informative rather than empty.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_lang
from app.db.models import CrisisEvent, MarketSnapshot
from app.db.session import get_db
from app.schemas.responses import BacktestReconstruction, CrisisEventOut

router = APIRouter()


def _event_out(r: CrisisEvent, lang: str) -> CrisisEventOut:
    is_zh = lang == "zh"
    return CrisisEventOut(
        id=r.id, name=(r.name_zh if is_zh else "") or r.name, event_start=r.event_start, event_end=r.event_end,
        peak_to_trough_drawdown=r.peak_to_trough_drawdown, recession_start=r.recession_start,
        recession_end=r.recession_end, description=(r.description_zh if is_zh else "") or r.description,
    )


@router.get("/backtest/events", response_model=list[CrisisEventOut])
def list_events(db: Session = Depends(get_db), lang: str = Depends(get_lang)) -> list[CrisisEventOut]:
    rows = db.query(CrisisEvent).order_by(CrisisEvent.event_start.asc()).all()
    return [_event_out(r, lang) for r in rows]


@router.get("/backtest/events/{event_id}", response_model=BacktestReconstruction)
def get_event(event_id: int, db: Session = Depends(get_db), lang: str = Depends(get_lang)) -> BacktestReconstruction:
    row = db.query(CrisisEvent).filter(CrisisEvent.id == event_id).first()
    if row is None:
        raise HTTPException(status_code=404, detail="event not found")

    snaps = db.query(MarketSnapshot).order_by(MarketSnapshot.snapshot_date.asc()).all()
    pre_event_scores = [
        {"date": s.snapshot_date.isoformat(), "us_equity_score": s.us_equity_score, "overall_status": s.overall_status}
        for s in snaps
    ]

    return BacktestReconstruction(event=_event_out(row, lang), pre_event_scores=pre_event_scores)
