from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.models import CfiSnapshot
from app.db.session import get_db
from app.jobs.cfi_pipeline import LOCK_IDS, compute_cfi, compute_lock_summaries
from app.schemas.cfi import CfiOverviewOut, CfiSnapshotOut

router = APIRouter()


@router.get("/cfi/overview", response_model=CfiOverviewOut)
def cfi_overview(db: Session = Depends(get_db)) -> CfiOverviewOut:
    lock_summaries = compute_lock_summaries(db)
    cfi_result = compute_cfi(lock_summaries)
    return CfiOverviewOut(
        cfi=cfi_result["cfi"], state=cfi_result["state"], demand_gate_active=cfi_result["demand_gate_active"],
        note=cfi_result["note"], locks=[lock_summaries[lock_id] for lock_id in LOCK_IDS],
    )


@router.get("/cfi/history", response_model=list[CfiSnapshotOut])
def cfi_history(db: Session = Depends(get_db), limit: int = 90) -> list[CfiSnapshotOut]:
    rows = db.query(CfiSnapshot).order_by(CfiSnapshot.snapshot_date.desc()).limit(limit).all()
    return [CfiSnapshotOut(snapshot_date=r.snapshot_date.isoformat(), cfi=r.cfi, state=r.state) for r in reversed(rows)]
