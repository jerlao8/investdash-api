"""Core ingestion -> scoring -> aggregation -> alerts pipeline.

Used by the startup seed-and-run, the APScheduler jobs (Section 47), and the
POST /api/admin/recalculate endpoint (Section 46) - all three just call run_full_pipeline().
"""

from __future__ import annotations

import secrets
from datetime import date, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import get_settings
from app.connectors import get_connector
from app.connectors.base import raw_payload_hash
from app.connectors.synthetic import MockParams
from app.db.models import (
    AlertEvent,
    Company,
    CompanyFundingScore,
    CompanyMetric,
    CrisisEvent,
    FeedItem,
    IndicatorDefinition,
    IndicatorObservation,
    IndicatorScore,
    MarketSnapshot,
    Source,
    User,
)
from app.jobs.backfill import backfill_market_snapshots
from app.scoring.aggregate import ScoredIndicator, compute_corroboration, compute_factor_scores, finalize_scores
from app.scoring.alerts import ObservationContext, build_feed_items
from app.scoring.fear_greed import compute_fear_greed_index
from app.scoring.health_score import compute_components
from app.security import hash_password
from app.seed.companies import COMPANIES
from app.seed.events import CRISIS_EVENTS
from app.seed.indicators import INDICATORS
from app.seed.indicators_zh import TRANSLATIONS as INDICATOR_TRANSLATIONS
from app.seed.sources import SOURCES

# Section 39 freshness model (converted to days; "daily stale after 36h" ~= 1.5 days).
FRESHNESS_DAYS = {"daily": 1.5, "weekly": 10, "monthly": 45, "quarterly": 120}

MOCK_PARAMS_BY_SLUG = {i["slug"]: MockParams(**i["mock"]) for i in INDICATORS}


def _sync_indicator_definitions(db: Session, source_id_by_key: dict[str, int]) -> None:
    """Upsert by slug, not "insert only if the table is empty" - a correction to the seed file
    (e.g. a mislabeled health_polarity) should take effect on the next restart/pipeline run,
    not require wiping the database. Mirrors Section 58's spirit: fixing scoring config is a
    config change, not a data-loss event."""
    existing_by_slug = {d.slug: d for d in db.query(IndicatorDefinition).all()}
    for meta in INDICATORS:
        row = existing_by_slug.get(meta["slug"])
        if row is None:
            row = IndicatorDefinition(slug=meta["slug"], active=True)
            db.add(row)
        row.name = meta["name"]
        row.category = meta["category"]
        row.subcategory = meta["subcategory"]
        row.source_id = source_id_by_key.get(meta["connector"])
        row.connector_key = meta["connector"]
        row.series_identifier = meta["series"]
        row.frequency = meta["frequency"]
        row.units = meta["units"]
        row.health_polarity = meta["health_polarity"]
        row.cluster = meta["cluster"]
        row.lead_lag = meta["lead_lag"]
        row.crisis_relevance = meta["crisis_relevance"]
        row.info_text = meta["info_text"]
        row.reading_guide = meta["reading_guide"]
        row.source_url = meta["source_url"]
        row.source_name = meta["source_name"]
        row.is_critical = meta["is_critical"]
        row.green_threshold = meta["green_threshold"]
        row.yellow_threshold = meta["yellow_threshold"]
        zh = INDICATOR_TRANSLATIONS.get(meta["slug"], {})
        row.name_zh = zh.get("name", "")
        row.info_text_zh = zh.get("info", "")
        row.reading_guide_zh = zh.get("guide", "")


def seed_and_sync(db: Session) -> None:
    source_id_by_key: dict[str, int] = {}
    existing_sources = {s.name: s for s in db.query(Source).all()}
    for s in SOURCES:
        row = existing_sources.get(s["name"])
        if row is None:
            row = Source(
                name=s["name"], base_url=s["base_url"], provider_type=s["provider_type"],
                requires_api_key=s["requires_api_key"], rate_limit=s["rate_limit"],
                license_notes=s["license_notes"], commercial_display_allowed=s["commercial_display_allowed"],
                priority=s["priority"],
            )
            db.add(row)
            db.flush()
        source_id_by_key[s["key"]] = row.id

    _sync_indicator_definitions(db, source_id_by_key)

    if db.query(Company).count() == 0:
        period_end = date.today().replace(day=1) - timedelta(days=1)  # end of last month, proxy quarter-end
        for c in COMPANIES:
            company = Company(name=c["name"], ticker=c["ticker"], cik=c["cik"], sector=c["sector"], subsector=c["subsector"], tier=c["tier"], active=True)
            db.add(company)
            db.flush()
            metrics = {
                "cash_and_equivalents": c["cash"],
                "short_term_investments": c["sti"],
                "total_debt": c["debt"],
                "short_term_debt": c["st_debt"],
                "interest_expense": c["interest"],
                "operating_cash_flow": c["ocf"],
                "capex": c["capex"],
                "revenue": c["revenue"],
                "ebitda": c["ebitda"],
                "free_cash_flow": c["ocf"] - c["capex"],
                "debt_maturities_next_12m": c["mat12"],
                "debt_maturities_next_24m": c["mat24"],
                "committed_capex_next_24m": c["capex24"],
                "revolver_available": c["revolver"],
            }
            for metric_name, value in metrics.items():
                db.add(
                    CompanyMetric(
                        company_id=company.id, metric_name=metric_name, period_end=period_end, filing_date=period_end,
                        value=float(value), unit="USD_millions", extraction_method="mock", confidence=60.0,
                        evidence_text="Synthetic MVP seed data - not a real filing figure.",
                    )
                )

    existing_events = {row.name: row for row in db.query(CrisisEvent).all()}
    for e in CRISIS_EVENTS:
        row = existing_events.get(e["name"])
        if row is None:
            row = CrisisEvent(name=e["name"])
            db.add(row)
        row.event_start = e["event_start"]
        row.event_end = e["event_end"]
        row.peak_to_trough_drawdown = e["peak_to_trough_drawdown"]
        row.recession_start = e["recession_start"]
        row.recession_end = e["recession_end"]
        row.description = e["description"]
        row.name_zh = e.get("name_zh", "")
        row.description_zh = e.get("description_zh", "")

    _seed_admin_user(db)

    db.commit()


def _seed_admin_user(db: Session) -> None:
    """Create the first admin account if none exists yet, so a fresh database always has
    someone who can log in and issue invite codes to everyone else."""
    if db.query(User).filter(User.role == "admin").count() > 0:
        return
    settings = get_settings()
    password = settings.initial_admin_password or secrets.token_urlsafe(12)
    db.add(User(username=settings.initial_admin_username, password_hash=hash_password(password), role="admin"))
    if not settings.initial_admin_password:
        print(
            "\n" + "=" * 60 +
            "\nGenerated initial admin account (INITIAL_ADMIN_PASSWORD was not set):"
            f"\n  username: {settings.initial_admin_username}\n  password: {password}"
            "\nSave this password now - it will not be shown again.\n" + "=" * 60 + "\n"
        )


def _ingest_indicator(db: Session, definition: IndicatorDefinition) -> IndicatorObservation | None:
    connector = get_connector(definition.connector_key)
    mock_params = MOCK_PARAMS_BY_SLUG.get(definition.slug)
    try:
        raw = connector.fetch(definition.series_identifier, mock_params=mock_params, years=12)
        observations = connector.normalize(raw)
    except Exception:  # noqa: BLE001 - a single bad indicator should never abort the whole pipeline
        return db.query(IndicatorObservation).filter(IndicatorObservation.indicator_id == definition.id).order_by(IndicatorObservation.observation_date.desc()).first()

    if not observations:
        return db.query(IndicatorObservation).filter(IndicatorObservation.indicator_id == definition.id).order_by(IndicatorObservation.observation_date.desc()).first()

    existing_dates = {
        d for (d,) in db.query(IndicatorObservation.observation_date).filter(IndicatorObservation.indicator_id == definition.id).all()
    }
    payload_hash = raw_payload_hash(raw.payload) if raw.payload else ""
    for obs in sorted(observations, key=lambda o: o.observation_date):
        if obs.observation_date in existing_dates:
            continue
        db.add(
            IndicatorObservation(
                indicator_id=definition.id, observation_date=obs.observation_date, value=obs.value,
                source_url=obs.source_url or definition.source_url, raw_payload_hash=payload_hash,
                is_preliminary=obs.is_preliminary,
            )
        )
    db.flush()
    return db.query(IndicatorObservation).filter(IndicatorObservation.indicator_id == definition.id).order_by(IndicatorObservation.observation_date.desc()).first()


def _score_indicator(db: Session, definition: IndicatorDefinition, latest_obs: IndicatorObservation) -> tuple[ScoredIndicator, ObservationContext] | None:
    today = date.today()
    rows = (
        db.query(IndicatorObservation.observation_date, IndicatorObservation.value)
        .filter(IndicatorObservation.indicator_id == definition.id)
        .order_by(IndicatorObservation.observation_date.asc())
        .all()
    )
    if len(rows) < 2:
        return None

    dates = [d for d, _ in rows]
    values_full = [v for _, v in rows]
    cutoff_5y = today - timedelta(days=365 * 5)
    cutoff_10y = today - timedelta(days=365 * 10)
    values_5y = [v for d, v in rows if d >= cutoff_5y] or values_full
    values_10y = [v for d, v in rows if d >= cutoff_10y] or values_full
    current = values_full[-1]

    components = compute_components(definition.slug, current, values_5y, values_10y, values_full, definition.health_polarity)

    expected_gap = FRESHNESS_DAYS.get(definition.frequency, 3)
    is_stale = (today - dates[-1]).days > expected_gap

    scored = ScoredIndicator(
        slug=definition.slug, cluster=definition.cluster, category=definition.category, components=components,
        green_threshold=definition.green_threshold, yellow_threshold=definition.yellow_threshold,
        is_stale=is_stale, indicator_id=definition.id, observation_id=latest_obs.id,
    )

    tail = values_full[-40:]
    change_1d = tail[-1] - tail[-2] if len(tail) >= 2 else None
    change_5d = tail[-1] - tail[-6] if len(tail) >= 6 else None
    change_1m = tail[-1] - tail[-21] if len(tail) >= 21 else None
    ctx = ObservationContext(
        slug=definition.slug, name=definition.name, name_zh=definition.name_zh or definition.name, value=current,
        change_1d=change_1d, change_5d=change_5d,
        change_1m=change_1m, source_url=latest_obs.source_url or definition.source_url, source_name=definition.source_name,
    )
    return scored, ctx


def _score_ratio(value: float, low: float, high: float) -> float:
    """Linear-clamp value in [low, high] onto a 0-10 sub-score."""
    if high == low:
        return 5.0
    frac = (value - low) / (high - low)
    return round(max(0.0, min(10.0, frac * 10)), 2)


def compute_company_funding_scores(db: Session) -> None:
    """Section 26 formulas: liquidity runway, debt-service coverage, capex coverage,
    maturity coverage, and expansion funding gap - converted into 0-10 sub-scores and an
    equal-weighted overall across all six."""
    companies = db.query(Company).filter(Company.active == True).all()  # noqa: E712
    today = date.today()
    db.query(CompanyFundingScore).filter(CompanyFundingScore.date == today).delete()

    for c in companies:
        rows = (
            db.query(CompanyMetric)
            .filter(CompanyMetric.company_id == c.id)
            .order_by(CompanyMetric.metric_name, CompanyMetric.period_end.desc())
            .all()
        )
        metrics: dict[str, float] = {}
        for r in rows:
            metrics.setdefault(r.metric_name, r.value)

        cash = metrics.get("cash_and_equivalents", 0.0)
        sti = metrics.get("short_term_investments", 0.0)
        revolver = metrics.get("revolver_available", 0.0)
        debt = metrics.get("total_debt", 0.0)
        interest = max(metrics.get("interest_expense", 0.0), 0.01)
        fcf = metrics.get("free_cash_flow", 0.0)
        ebitda = metrics.get("ebitda", 0.0)
        revenue = max(metrics.get("revenue", 0.0), 1.0)
        ocf = metrics.get("operating_cash_flow", 0.0)
        capex = max(metrics.get("capex", 0.0), 0.01)
        mat12 = metrics.get("debt_maturities_next_12m", 0.0)
        mat24 = metrics.get("debt_maturities_next_24m", 0.0)
        capex24 = metrics.get("committed_capex_next_24m", 0.0)

        liquidity = cash + sti + revolver
        core_cash_burn = max(0.0, -fcf)
        coverage_months = liquidity / (core_cash_burn / 12) if core_cash_burn > 0 else 999.0

        cash_interest_coverage = ebitda / interest
        forecast_fcf_24m = fcf * 2  # naive 2yr extrapolation - no separate guidance data seeded
        expansion_funding_gap = mat24 + capex24 - liquidity - forecast_fcf_24m

        if fcf >= 0:
            liquidity_score = _score_ratio(cash / max(debt, 1.0), 0.05, 1.0)
        else:
            liquidity_score = _score_ratio(coverage_months, 0, 24)

        debt_score = _score_ratio(cash_interest_coverage, 0, 15)
        fcf_score = _score_ratio(fcf / revenue, -0.25, 0.25)
        capex_score = _score_ratio(ocf / capex, 0.5, 2.0)
        maturity_24m_coverage = liquidity / mat24 if mat24 > 0 else 999.0
        maturity_score = _score_ratio(maturity_24m_coverage, 0, 3) if mat24 > 0 else 10.0

        # The other five components are backward/short-term (current cash vs. current debt,
        # current EBITDA vs. current interest) - they can all look fine even when a company has
        # a large FORWARD funding need, since committed capex over the next 24 months isn't
        # captured anywhere else. expansion_funding_gap is the one genuinely forward-looking
        # metric (Section 26 calls it out specifically: "a positive number is a funding need"),
        # so it must be scored and folded into the overall average, not just displayed
        # alongside it - a big funding gap should visibly pull the score down.
        gap_ratio = expansion_funding_gap / revenue
        funding_gap_score = _score_ratio(-gap_ratio, -0.15, 0.20)

        overall = round(
            (liquidity_score + debt_score + fcf_score + capex_score + maturity_score + funding_gap_score) / 6, 2
        )

        db.add(
            CompanyFundingScore(
                company_id=c.id, date=today, liquidity_score=liquidity_score, debt_score=debt_score,
                fcf_score=fcf_score, capex_score=capex_score, maturity_score=maturity_score,
                funding_gap_score=funding_gap_score,
                funding_gap=round(expansion_funding_gap, 1), overall_score=overall,
            )
        )
    db.flush()


def run_full_pipeline(db: Session) -> dict:
    settings = get_settings()
    seed_and_sync(db)

    definitions = db.query(IndicatorDefinition).filter(IndicatorDefinition.active == True).all()  # noqa: E712

    scored_list: list[ScoredIndicator] = []
    contexts: dict[str, ObservationContext] = {}

    for definition in definitions:
        latest_obs = _ingest_indicator(db, definition)
        if latest_obs is None:
            continue
        result = _score_indicator(db, definition, latest_obs)
        if result is None:
            continue
        scored, ctx = result
        scored_list.append(scored)
        contexts[definition.slug] = ctx

    compute_corroboration(scored_list)
    finalize_scores(scored_list)

    for s in scored_list:
        db.add(
            IndicatorScore(
                indicator_id=s.indicator_id, observation_id=s.observation_id, health_score_0_100=s.health_score,
                stress_percentile=s.stress_percentile, z_score=s.components.z_score, velocity_score=s.components.velocity,
                persistence_score=s.components.persistence, color_state=s.color, direction=s.components.direction,
                raw_trend=s.components.raw_trend,
                confidence=0.0 if s.is_stale else 100.0, algorithm_version=settings.algorithm_version,
            )
        )

    factor_scores = compute_factor_scores(scored_list)
    scored_by_slug = {s.slug: s for s in scored_list}
    fear_greed = compute_fear_greed_index(scored_by_slug)

    today = date.today()
    db.query(MarketSnapshot).filter(MarketSnapshot.snapshot_date == today).delete()
    db.add(
        MarketSnapshot(
            snapshot_date=today,
            us_equity_score=factor_scores.overall_0_10,
            us_macro_score=factor_scores.scores_0_10.get("us_macro", 5.0),
            global_score=factor_scores.scores_0_10.get("global_spillover", 5.0),
            liquidity_score=factor_scores.scores_0_10.get("liquidity", 5.0),
            credit_score=factor_scores.scores_0_10.get("credit_funding", 5.0),
            ai_funding_score=factor_scores.ai_funding_0_10,
            valuation_score=factor_scores.scores_0_10.get("valuation_positioning", 5.0),
            equity_internals_score=factor_scores.scores_0_10.get("equity_internals", 5.0),
            fear_greed_index=fear_greed,
            overall_status=factor_scores.overall_status,
            algorithm_version=settings.algorithm_version,
        )
    )

    feed_items = build_feed_items(scored_list, contexts, today)
    db.query(FeedItem).filter(FeedItem.date == today).delete()
    db.query(AlertEvent).filter(func.date(AlertEvent.timestamp) == today).delete()
    db.flush()

    for item in feed_items:
        alert = AlertEvent(
            severity=item["severity"], event_type=item["event_type"], cluster=item.get("cluster", ""),
            indicator_ids=[], headline=item["headline"], summary=item["summary"],
            headline_zh=item.get("headline_zh", ""), summary_zh=item.get("summary_zh", ""),
            direction=item.get("direction", "negative"),
            equity_implication=item.get("equity_implication", ""), equity_implication_zh=item.get("equity_implication_zh", ""),
            source_urls=item.get("source_urls", []),
            dedupe_key=item["dedupe_key"], status="active",
        )
        db.add(alert)
        db.flush()
        db.add(
            FeedItem(
                date=today, priority=item.get("priority", 3), category=item.get("category", "General"),
                category_zh=item.get("category_zh", ""),
                headline=item["headline"], summary=item["summary"],
                headline_zh=item.get("headline_zh", ""), summary_zh=item.get("summary_zh", ""),
                related_alert_id=alert.id,
                source_url=(item.get("source_urls") or [""])[0],
            )
        )

    compute_company_funding_scores(db)

    db.commit()

    backfilled = backfill_market_snapshots(db)

    return {
        "indicators_scored": len(scored_list),
        "overall_score": factor_scores.overall_0_10,
        "status": factor_scores.overall_status,
        "feed_items": len(feed_items),
        "backfilled_snapshots": backfilled,
    }
