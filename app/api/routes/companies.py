from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.models import Company, CompanyFundingScore, CompanyMetric
from app.db.session import get_db
from app.schemas.responses import CompanyDetail, CompanyOut

router = APIRouter()


def _latest_funding_score(db: Session, company_id: int) -> CompanyFundingScore | None:
    return (
        db.query(CompanyFundingScore)
        .filter(CompanyFundingScore.company_id == company_id)
        .order_by(CompanyFundingScore.date.desc())
        .first()
    )


@router.get("/companies", response_model=list[CompanyOut])
def list_companies(db: Session = Depends(get_db), tier: str | None = None) -> list[CompanyOut]:
    q = db.query(Company).filter(Company.active == True)  # noqa: E712
    if tier:
        q = q.filter(Company.tier == tier)
    companies = q.all()
    out = []
    for c in companies:
        fs = _latest_funding_score(db, c.id)
        out.append(
            CompanyOut(
                id=c.id, name=c.name, ticker=c.ticker, sector=c.sector, subsector=c.subsector, tier=c.tier,
                overall_score=fs.overall_score if fs else None, liquidity_score=fs.liquidity_score if fs else None,
                debt_score=fs.debt_score if fs else None, fcf_score=fs.fcf_score if fs else None,
                capex_score=fs.capex_score if fs else None, maturity_score=fs.maturity_score if fs else None,
                funding_gap=fs.funding_gap if fs else None, funding_gap_score=fs.funding_gap_score if fs else None,
            )
        )
    return out


@router.get("/companies/{ticker}", response_model=CompanyDetail)
def get_company(ticker: str, db: Session = Depends(get_db)) -> CompanyDetail:
    c = db.query(Company).filter(Company.ticker == ticker.upper()).first()
    if c is None:
        raise HTTPException(status_code=404, detail="company not found")
    fs = _latest_funding_score(db, c.id)
    rows = (
        db.query(CompanyMetric)
        .filter(CompanyMetric.company_id == c.id)
        .order_by(CompanyMetric.metric_name, CompanyMetric.period_end.desc())
        .all()
    )
    metrics: dict[str, float] = {}
    for r in rows:
        metrics.setdefault(r.metric_name, r.value)

    return CompanyDetail(
        id=c.id, name=c.name, ticker=c.ticker, sector=c.sector, subsector=c.subsector, tier=c.tier,
        overall_score=fs.overall_score if fs else None, liquidity_score=fs.liquidity_score if fs else None,
        debt_score=fs.debt_score if fs else None, fcf_score=fs.fcf_score if fs else None,
        capex_score=fs.capex_score if fs else None, maturity_score=fs.maturity_score if fs else None,
        funding_gap=fs.funding_gap if fs else None, funding_gap_score=fs.funding_gap_score if fs else None,
        metrics=metrics,
    )
