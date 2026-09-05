from datetime import date
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.connectors.base import RawObservation
from app.db.models import Company, CompanyMetric, IndicatorDefinition, IndicatorObservation
from app.db.session import Base
from app.jobs.cfi_pipeline import CAPEX_TAGS, OCF_TAGS, _fetch_xbrl_metric, compute_l6_company_health, compute_lock_summaries


def _make_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine, tables=[Company.__table__, CompanyMetric.__table__])
    return sessionmaker(bind=engine)()


def _make_full_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        bind=engine,
        tables=[Company.__table__, CompanyMetric.__table__, IndicatorDefinition.__table__, IndicatorObservation.__table__],
    )
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


class _FakeConnector:
    """Records every .fetch() call - stands in for SecConnector to prove
    _fetch_xbrl_metric fetches a company's multi-MB company-facts document at most once per
    ingest_l6_financials() run, not once per candidate tag."""

    def __init__(self):
        self.fetch_calls: list[str] = []

    def fetch(self, series_identifier: str):
        self.fetch_calls.append(series_identifier)
        return RawObservation(series_identifier=series_identifier, payload={"facts": {"us-gaap": {}}}, source_url="")

    def normalize(self, raw):
        return []


def test_fetch_xbrl_metric_fetches_company_facts_at_most_once_per_run():
    """A mega-cap's company-facts JSON is ~4-5MB; the old code re-fetched and re-parsed it
    once per candidate tag (capex has 2, ocf has 2 - up to 4x per company), which is what
    drove a full CFI run to exhaust the free-tier instance's memory/CPU and hang. One live
    fetch per company, cached across every tag lookup in the same run."""
    db = _make_session()
    company = Company(name="Microsoft", ticker="MSFT", cik="0000789019", sector="Hyperscaler", subsector="Cloud", tier="hyperscalers", lock_id="L6", active=True)
    db.add(company)
    db.flush()

    fake = _FakeConnector()
    facts_cache: dict[str, dict] = {}
    with patch("app.jobs.cfi_pipeline.get_connector", return_value=fake):
        _fetch_xbrl_metric(db, company, CAPEX_TAGS, "capex", facts_cache)
        _fetch_xbrl_metric(db, company, OCF_TAGS, "operating_cash_flow", facts_cache)

    assert len(fake.fetch_calls) == 1


def test_lock_summaries_list_tracked_companies_even_without_a_per_company_score():
    """L3's health is one macro-level credit-spread proxy shared across every company tagged
    to it, not an individual score per company - but the UI still needs to answer "which 9
    companies" for a lock whose company_count is 9. tracked_companies must be populated for
    every lock, independent of whether that lock has any per-company score computed."""
    db = _make_full_session()
    db.add(Company(name="Blackstone", ticker="BX", sector="Financials", subsector="Private Credit", tier="cfi_only", lock_id="L3", cfi_role="Private Credit", active=True))
    db.add(Company(name="Moody's", ticker="MCO", sector="Financials", subsector="Rating Agency", tier="cfi_only", lock_id="L3", cfi_role="Rating Agency", active=True))
    db.commit()

    summaries = compute_lock_summaries(db)

    assert summaries["L3"]["health"] is None  # no hy-oas/ig-oas indicator data seeded - no score
    assert summaries["L3"]["company_count"] == 2
    tickers = {c["ticker"] for c in summaries["L3"]["tracked_companies"]}
    assert tickers == {"BX", "MCO"}
    assert all(c["cfi_role"] for c in summaries["L3"]["tracked_companies"])
