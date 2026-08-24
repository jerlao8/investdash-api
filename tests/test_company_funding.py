from datetime import date

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.models import Company, CompanyFundingScore, CompanyMetric
from app.db.session import Base
from app.jobs.pipeline import compute_company_funding_scores


def _make_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine, tables=[Company.__table__, CompanyMetric.__table__, CompanyFundingScore.__table__])
    return sessionmaker(bind=engine)()


def _seed_company(db, ticker, metrics_overrides):
    company = Company(name=ticker, ticker=ticker, sector="Tech", subsector="Tech", tier="hyperscalers", active=True)
    db.add(company)
    db.flush()
    period_end = date(2026, 6, 30)
    base_metrics = {
        "cash_and_equivalents": 70000, "short_term_investments": 13000, "revolver_available": 0,
        "total_debt": 58000, "interest_expense": 2500, "operating_cash_flow": 100000, "capex": 75000,
        "revenue": 590000, "ebitda": 105000, "free_cash_flow": 25000,
        "debt_maturities_next_12m": 8000, "debt_maturities_next_24m": 13000, "committed_capex_next_24m": 20000,
    }
    base_metrics.update(metrics_overrides)
    for name, value in base_metrics.items():
        db.add(CompanyMetric(company_id=company.id, metric_name=name, period_end=period_end, value=float(value), unit="USD_millions"))
    db.commit()
    return company


def test_large_funding_gap_pulls_overall_score_down():
    db = _make_session()
    # Same liquidity/debt/FCF profile, but this one has committed capex far beyond what
    # liquidity + forecast FCF can cover over the next 24 months (mirrors the AMZN case:
    # $160B committed capex vs. $83B liquidity + $50B forecast FCF -> a real funding gap).
    modest_capex = _seed_company(db, "MODEST", {"committed_capex_next_24m": 20000})
    huge_capex = _seed_company(db, "HUGE", {"committed_capex_next_24m": 160000})

    compute_company_funding_scores(db)
    db.commit()

    modest_score = db.query(CompanyFundingScore).filter(CompanyFundingScore.company_id == modest_capex.id).first()
    huge_score = db.query(CompanyFundingScore).filter(CompanyFundingScore.company_id == huge_capex.id).first()

    assert huge_score.funding_gap > modest_score.funding_gap
    assert huge_score.funding_gap_score < modest_score.funding_gap_score
    # The critical assertion: a real forward funding need must show up in the OVERALL score,
    # not just sit unused in the funding_gap field alongside an unmoved overall_score.
    assert huge_score.overall_score < modest_score.overall_score
