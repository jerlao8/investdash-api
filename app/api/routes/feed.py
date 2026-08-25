from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_lang
from app.db.models import AlertEvent, FeedItem
from app.db.session import get_db
from app.schemas.responses import FeedItemOut
from app.timeutil import today_pt

router = APIRouter()


@router.get("/feed", response_model=list[FeedItemOut])
def get_feed(
    db: Session = Depends(get_db),
    lang: str = Depends(get_lang),
    days: int = Query(14, ge=1, le=365),
    category: str | None = None,
    limit: int = Query(100, ge=1, le=500),
) -> list[FeedItemOut]:
    cutoff = today_pt() - timedelta(days=days)
    q = db.query(FeedItem).filter(FeedItem.date >= cutoff)
    if category:
        q = q.filter(FeedItem.category == category)
    rows = q.order_by(FeedItem.date.desc(), FeedItem.priority.asc()).limit(limit).all()

    alert_ids = [r.related_alert_id for r in rows if r.related_alert_id]
    alerts = {a.id: a for a in db.query(AlertEvent).filter(AlertEvent.id.in_(alert_ids)).all()} if alert_ids else {}

    is_zh = lang == "zh"
    out = []
    for r in rows:
        alert = alerts.get(r.related_alert_id) if r.related_alert_id else None
        out.append(
            FeedItemOut(
                id=r.id, date=r.date, posted_at=r.created_at, priority=r.priority,
                category=(r.category_zh if is_zh else "") or r.category,
                headline=(r.headline_zh if is_zh else "") or r.headline,
                summary=(r.summary_zh if is_zh else "") or r.summary,
                source_url=r.source_url,
                severity=alert.severity if alert else None,
                direction=alert.direction if alert else None,
                equity_implication=((alert.equity_implication_zh if is_zh else "") or alert.equity_implication) if alert else None,
            )
        )
    return out
