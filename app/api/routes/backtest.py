"""Backtesting endpoints (PRD Section 41).

For each crisis event, reconstruct the dashboard's applied U.S. Equity Health score as of
event_start (crash/peak) by re-running today's scoring path against observation history
truncated to that date. That is not true vintage/ALFRED reconstruction — percentiles use
history known as of the as-of date with the current algorithm — but it answers "what would
my health score have been at failure."

Detail views also chart reconstructed scores across a window around the event.
"""

from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_lang
from app.db.models import CrisisEvent
from app.db.session import get_db
from app.jobs.backfill import load_observation_history, reconstruct_score_series, us_equity_health_as_of
from app.schemas.responses import BacktestReconstruction, CrisisEventOut

router = APIRouter()


def _event_out(
    r: CrisisEvent,
    lang: str,
    *,
    us_equity_score_at_start: float | None = None,
    overall_status_at_start: str | None = None,
) -> CrisisEventOut:
    is_zh = lang == "zh"
    return CrisisEventOut(
        id=r.id,
        name=(r.name_zh if is_zh else "") or r.name,
        event_start=r.event_start,
        event_end=r.event_end,
        peak_to_trough_drawdown=r.peak_to_trough_drawdown,
        recession_start=r.recession_start,
        recession_end=r.recession_end,
        description=(r.description_zh if is_zh else "") or r.description,
        us_equity_score_at_start=us_equity_score_at_start,
        overall_status_at_start=overall_status_at_start,
    )


@router.get("/backtest/events", response_model=list[CrisisEventOut])
def list_events(db: Session = Depends(get_db), lang: str = Depends(get_lang)) -> list[CrisisEventOut]:
    rows = db.query(CrisisEvent).order_by(CrisisEvent.event_start.asc()).all()
    definitions, history_by_id = load_observation_history(db)
    out: list[CrisisEventOut] = []
    for r in rows:
        point = us_equity_health_as_of(definitions, history_by_id, r.event_start) if definitions else None
        out.append(
            _event_out(
                r,
                lang,
                us_equity_score_at_start=point["us_equity_score"] if point else None,
                overall_status_at_start=point["overall_status"] if point else None,
            )
        )
    return out


@router.get("/backtest/events/{event_id}", response_model=BacktestReconstruction)
def get_event(event_id: int, db: Session = Depends(get_db), lang: str = Depends(get_lang)) -> BacktestReconstruction:
    row = db.query(CrisisEvent).filter(CrisisEvent.id == event_id).first()
    if row is None:
        raise HTTPException(status_code=404, detail="event not found")

    definitions, history_by_id = load_observation_history(db)
    point = us_equity_health_as_of(definitions, history_by_id, row.event_start) if definitions else None

    # Chart ~6 months before peak through trough (or +3 months if no end date).
    chart_start = row.event_start - timedelta(days=180)
    chart_end = row.event_end or (row.event_start + timedelta(days=90))
    span_days = (chart_end - chart_start).days
    if span_days > 500:
        step = 30
    elif span_days > 200:
        step = 14
    else:
        step = 7

    pre_event_scores = (
        reconstruct_score_series(definitions, history_by_id, chart_start, chart_end, step_days=step)
        if definitions
        else []
    )

    return BacktestReconstruction(
        event=_event_out(
            row,
            lang,
            us_equity_score_at_start=point["us_equity_score"] if point else None,
            overall_status_at_start=point["overall_status"] if point else None,
        ),
        pre_event_scores=pre_event_scores,
    )
