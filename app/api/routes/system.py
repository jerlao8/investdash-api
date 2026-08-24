from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_latest_scores
from app.connectors import CONNECTOR_REGISTRY
from app.db.models import IndicatorDefinition, IndicatorScore, MarketSnapshot
from app.db.session import get_db
from app.schemas.responses import DataHealthOut, DataHealthSource

router = APIRouter()


@router.get("/system/data-health", response_model=DataHealthOut)
def data_health(db: Session = Depends(get_db)) -> DataHealthOut:
    sources = [
        DataHealthSource(name=c.name, mode=c.mode, ok=c.source_health().ok, detail=c.source_health().detail)
        for c in CONNECTOR_REGISTRY.values()
    ]

    scores = get_latest_scores(db)
    stale_ids = {iid for iid, s in scores.items() if s.color_state == "gray"}
    defs = db.query(IndicatorDefinition).filter(IndicatorDefinition.id.in_(stale_ids)).all() if stale_ids else []

    latest_snap = db.query(MarketSnapshot).order_by(MarketSnapshot.snapshot_date.desc()).first()

    return DataHealthOut(
        sources=sources,
        stale_indicators=[d.name for d in defs],
        total_indicators=db.query(IndicatorDefinition).filter(IndicatorDefinition.active == True).count(),  # noqa: E712
        last_pipeline_run=latest_snap.created_at if latest_snap else None,
    )
