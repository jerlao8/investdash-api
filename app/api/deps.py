from __future__ import annotations

from datetime import date, datetime

from fastapi import Depends, HTTPException, Request
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.models import FavoriteIndicator, IndicatorObservation, IndicatorScore, User
from app.db.session import get_db
from app.security import decode_access_token


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="not authenticated")
    payload = decode_access_token(auth_header.removeprefix("Bearer "))
    if payload is None:
        raise HTTPException(status_code=401, detail="invalid or expired token")
    user = db.query(User).filter(User.id == int(payload["sub"])).first()
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="user not found or disabled")
    user.last_active_at = datetime.utcnow()
    db.commit()
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="admin access required")
    return user


def get_lang(user: User = Depends(get_current_user)) -> str:
    return user.language or "en"


def get_favorited_indicator_ids(db: Session, user_id: int) -> set[int]:
    rows = db.query(FavoriteIndicator.indicator_id).filter(FavoriteIndicator.user_id == user_id).all()
    return {r[0] for r in rows}


def get_latest_scores(db: Session) -> dict[int, IndicatorScore]:
    """Latest IndicatorScore per indicator, computed as a DB-side GROUP BY MAX join rather
    than pulling every historical score row into Python - with the pipeline accumulating one
    IndicatorScore row per indicator per run, a naive full-table scan gets slower every day."""
    subq = (
        db.query(IndicatorScore.indicator_id, func.max(IndicatorScore.calculated_at).label("max_calculated_at"))
        .group_by(IndicatorScore.indicator_id)
        .subquery()
    )
    rows = (
        db.query(IndicatorScore)
        .join(
            subq,
            (IndicatorScore.indicator_id == subq.c.indicator_id)
            & (IndicatorScore.calculated_at == subq.c.max_calculated_at),
        )
        .all()
    )
    out: dict[int, IndicatorScore] = {}
    for r in rows:
        out.setdefault(r.indicator_id, r)  # setdefault guards against a rare exact-timestamp tie
    return out


def get_latest_observations(db: Session) -> dict[int, IndicatorObservation]:
    """Latest IndicatorObservation per indicator - same DB-side aggregation rationale as
    get_latest_scores. A prior version pulled the entire observations table (hundreds of
    thousands of rows across 12 years of backfilled history x ~107 indicators) into Python
    on every /api/indicators list call; this scales with indicator count instead."""
    subq = (
        db.query(IndicatorObservation.indicator_id, func.max(IndicatorObservation.observation_date).label("max_date"))
        .group_by(IndicatorObservation.indicator_id)
        .subquery()
    )
    rows = (
        db.query(IndicatorObservation)
        .join(
            subq,
            (IndicatorObservation.indicator_id == subq.c.indicator_id)
            & (IndicatorObservation.observation_date == subq.c.max_date),
        )
        .all()
    )
    out: dict[int, IndicatorObservation] = {}
    for r in rows:
        out.setdefault(r.indicator_id, r)
    return out


def get_latest_observation_for(db: Session, indicator_id: int) -> IndicatorObservation | None:
    return (
        db.query(IndicatorObservation)
        .filter(IndicatorObservation.indicator_id == indicator_id)
        .order_by(IndicatorObservation.observation_date.desc())
        .first()
    )


def get_latest_score_for(db: Session, indicator_id: int) -> IndicatorScore | None:
    return (
        db.query(IndicatorScore)
        .filter(IndicatorScore.indicator_id == indicator_id)
        .order_by(IndicatorScore.calculated_at.desc())
        .first()
    )


def get_extreme_ranges_since(db: Session, since: date) -> dict[int, tuple[float, float]]:
    """min/max per indicator over a date range, aggregated in the database (not fetched row by
    row into Python) - the same lesson as get_latest_observations: never pull thousands of
    historical rows per indicator into Python when the DB can reduce it to one row each."""
    rows = (
        db.query(
            IndicatorObservation.indicator_id,
            func.min(IndicatorObservation.value),
            func.max(IndicatorObservation.value),
        )
        .filter(IndicatorObservation.observation_date >= since)
        .group_by(IndicatorObservation.indicator_id)
        .all()
    )
    return {indicator_id: (lo, hi) for indicator_id, lo, hi in rows}


def get_extreme_range_for(db: Session, indicator_id: int, since: date) -> tuple[float, float] | None:
    row = (
        db.query(func.min(IndicatorObservation.value), func.max(IndicatorObservation.value))
        .filter(IndicatorObservation.indicator_id == indicator_id, IndicatorObservation.observation_date >= since)
        .first()
    )
    if row is None or row[0] is None:
        return None
    return row[0], row[1]


def compute_changes(db: Session, indicator_id: int) -> tuple[float | None, float | None, float | None]:
    rows = (
        db.query(IndicatorObservation.value)
        .filter(IndicatorObservation.indicator_id == indicator_id)
        .order_by(IndicatorObservation.observation_date.desc())
        .limit(40)
        .all()
    )
    vals = [v for (v,) in rows][::-1]
    change_1d = vals[-1] - vals[-2] if len(vals) >= 2 else None
    change_5d = vals[-1] - vals[-6] if len(vals) >= 6 else None
    change_1m = vals[-1] - vals[-21] if len(vals) >= 21 else None
    return change_1d, change_5d, change_1m
