from datetime import date

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.models import Company, CompanyMetric
from app.db.session import Base
from app.jobs.cfi_pipeline import compute_l6_company_health


def _make_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine, tables=[Company.__table__, CompanyMetric.__table__])
    return sessionmaker(bind=engine)()


def test_l6_health_ignores_ai_company_monitor_mock_rows_sharing_the_same_metric_name():
    """MSFT/AMZN/GOOGL/META/ORCL/AAPL are seeded by BOTH the AI Company Monitor (mock capex/
    operating_cash_flow in USD_millions, dated "end of last month") and the CFI pipeline's
    real SEC XBRL ingestion (raw USD, dated the actual filed quarter-end) - same company_id,
    same metric_name. The mock row's artificially-recent period_end must not get picked up as
    the "latest quarter" and diffed against a real prior quarter (that produced a nonsensical
    ~-100% QoQ swing on every single L6 company before the extraction_method="xbrl" filter)."""
    db = _make_session()
    company = Company(name="Microsoft", ticker="MSFT", sector="Hyperscaler", subsector="Cloud", tier="hyperscalers", lock_id="L6", active=True)
    db.add(company)
    db.flush()

    real_quarters = [
        (date(2025, 9, 30), 19394000000.0),
        (date(2025, 12, 31), 29876000000.0),
        (date(2026, 3, 31), 30876000000.0),
        (date(2026, 6, 30), 35802000000.0),
    ]
    for period_end, value in real_quarters:
        db.add(CompanyMetric(
            company_id=company.id, metric_name="capex", period_end=period_end, value=value,
            unit="USD", extraction_method="xbrl",
        ))
        db.add(CompanyMetric(
            company_id=company.id, metric_name="operating_cash_flow", period_end=period_end, value=value * 1.5,
            unit="USD", extraction_method="xbrl",
        ))

    # The AI Company Monitor's synthetic seed row - tiny USD_millions figure, but dated LATER
    # than every real filed quarter above (mirrors seed_and_sync's "end of last month" period_end).
    db.add(CompanyMetric(
        company_id=company.id, metric_name="capex", period_end=date(2026, 8, 31), value=55000.0,
        unit="USD_millions", extraction_method="mock",
    ))
    db.add(CompanyMetric(
        company_id=company.id, metric_name="operating_cash_flow", period_end=date(2026, 8, 31), value=110000.0,
        unit="USD_millions", extraction_method="mock",
    ))
    db.commit()

    result = compute_l6_company_health(db, company)

    assert result is not None
    assert result["capex_latest"] == 35802000000.0
    assert result["capex_qoq_growth_pct"] > -50.0  # real QoQ growth, not the ~-100% mock-collision artifact
