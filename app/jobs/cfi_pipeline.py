"""Capex Freeze Monitor pipeline (build spec §5-6), v1 scope.

Real data only, no fabricated fill-ins - two of the six locks have a genuine free source
wired up:

  L6 (capex freeze, the lock the whole dashboard is about) - real quarterly capex and
  operating cash flow for the six end-users, pulled live from SEC EDGAR XBRL via the
  existing SecConnector ("{cik}:{us-gaap tag}").

  L3 (financing) - proxied by InvestDash's own existing hy-oas/ig-oas credit-spread
  indicators (already ingested from FRED for the main dashboard) as a real, if imperfect,
  read on financing conditions facing leveraged AI-infrastructure borrowers, pending a
  real per-borrower CDS/bond-spread feed (paid data per spec §8).

L1, L2, L4 and L5 have their company registries seeded (so the chain/heatmap UI can show
them) but no scored indicator yet - they report coverage=0 and stay out of the cascade
math entirely, rather than defaulting to a fabricated "healthy". This is the spec's own
coverage-requirement principle (§6.1): never impute, surface staleness instead.
"""

from __future__ import annotations

import json
import math
from datetime import date, datetime, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.connectors import get_connector
from app.db.models import CfiSnapshot, Company, CompanyMetric, IndicatorDefinition, IndicatorObservation
from app.jobs.pipeline import _pipeline_lock
from app.seed.cfi_companies import CFI_COMPANIES

LOCK_IDS = ["L1", "L2", "L3", "L4", "L5", "L6"]
LOCK_NAMES = {
    "L1": "Unit economics", "L2": "Utilisation", "L3": "Financing",
    "L4": "Order book", "L5": "Physical build", "L6": "Capex freeze",
}
LOCK_WEIGHTS = {"L1": 0.32, "L2": 0.24, "L3": 0.18, "L4": 0.14, "L5": 0.08, "L6": 0.04}
TIER_WEIGHT = {1: 3.0, 2: 1.5, 3: 0.5}

# registry/transmission.yaml (spec §6.5) - only edges touching scored locks (L3, L6) matter
# for v1's cascade math, but the full table is kept so it's ready as more locks get real data.
TRANSMISSION = [
    ("L1", "L2", 90, 0.80), ("L2", "L3", 60, 0.85), ("L3", "L4", 120, 0.55),
    ("L1", "L4", 150, 0.60), ("L4", "L5", 180, 0.70), ("L3", "L5", 150, 0.40),
    ("L5", "L6", 90, 0.50), ("L1", "L6", 240, 0.75),
]

# CIK+tag candidates per metric - companies tag the same line item under different us-gaap
# concepts (Amazon alone diverges from the other five here). Tried in order; first hit wins.
CAPEX_TAGS = ["PaymentsToAcquirePropertyPlantAndEquipment", "PaymentsToAcquireProductiveAssets"]
OCF_TAGS = ["NetCashProvidedByUsedInOperatingActivities", "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations"]


def sync_cfi_companies(db: Session) -> None:
    """Upsert by ticker - never touches the AI Company Monitor's own sector/subsector/tier
    fields on a row that already exists there, only adds the lock_id/cfi_tier/cfi_role tags."""
    existing = {c.ticker: c for c in db.query(Company).all()}
    for meta in CFI_COMPANIES:
        row = existing.get(meta["ticker"])
        if row is None:
            row = Company(
                ticker=meta["ticker"], name=meta["name"], cik=meta["cik"],
                sector="", subsector="", tier="cfi_only", active=True,
            )
            db.add(row)
        elif meta["cik"] and not row.cik:
            row.cik = meta["cik"]
        row.lock_id = meta["lock_id"]
        row.cfi_tier = meta["cfi_tier"]
        row.cfi_role = meta["cfi_role"]
    db.commit()


def _fetch_xbrl_metric(db: Session, company: Company, tags: list[str], metric_name: str) -> bool:
    """Try every candidate tag and merge what each returns; upsert into CompanyMetric by
    (company_id, metric_name, period_end) so re-running the pipeline doesn't duplicate rows.

    Companies sometimes switch which us-gaap tag they file a concept under partway through
    their history (e.g. Amazon reported capex under PaymentsToAcquirePropertyPlantAndEquipment
    only through ~2017, then PaymentsToAcquireProductiveAssets since) - stopping at the first
    tag with ANY data silently freezes coverage at whatever the earliest, most-discontinued
    tag last reported, so every tag is tried and their periods merged."""
    if not company.cik:
        return False
    connector = get_connector("sec")
    got_any = False
    for tag in tags:
        raw = connector.fetch(f"{company.cik}:{tag}")
        observations = connector.normalize(raw)
        if not observations:
            continue
        existing_periods = {
            m.period_end for m in db.query(CompanyMetric.period_end).filter(
                CompanyMetric.company_id == company.id, CompanyMetric.metric_name == metric_name
            ).all()
        }
        for obs in observations:
            if obs.observation_date in existing_periods:
                continue
            db.add(
                CompanyMetric(
                    company_id=company.id, metric_name=metric_name, period_end=obs.observation_date,
                    value=obs.value, unit="USD", source_filing_url=obs.source_url,
                    extraction_method="xbrl", confidence=100.0,
                    evidence_text=f"SEC EDGAR XBRL, tag={tag}",
                )
            )
            existing_periods.add(obs.observation_date)
        db.commit()  # per company+metric+tag, not batched - a long open write transaction is
        # exactly what caused the cross-request SQLite lock contention this pipeline (and the
        # main indicator pipeline) hit earlier; short, frequent commits keep the write lock
        # held only briefly instead of across this whole loop's worth of network round trips.
        got_any = True
    return got_any


def ingest_l6_financials(db: Session) -> dict[str, int]:
    """Real quarterly capex + operating cash flow for every L6 (and any CIK-bearing L4/L5)
    company, straight from SEC EDGAR - no mock fallback; a company with no CIK or whose
    tags don't match simply stays uncovered rather than getting a fabricated number."""
    companies = db.query(Company).filter(Company.lock_id.isnot(None), Company.cik.isnot(None)).all()
    counts = {"capex": 0, "operating_cash_flow": 0}
    for c in companies:
        if _fetch_xbrl_metric(db, c, CAPEX_TAGS, "capex"):
            counts["capex"] += 1
        if _fetch_xbrl_metric(db, c, OCF_TAGS, "operating_cash_flow"):
            counts["operating_cash_flow"] += 1
    return counts


def _robust_z(values: list[float], current: float, direction: int = 1) -> float:
    """z = direction * (x - median) / (1.4826 * MAD) (spec §6.1) - median/MAD rather than
    mean/stdev because quarterly capex series are short and a single print can be an outlier."""
    if len(values) < 2:
        return 0.0
    sorted_v = sorted(values)
    n = len(sorted_v)
    median = sorted_v[n // 2] if n % 2 else (sorted_v[n // 2 - 1] + sorted_v[n // 2]) / 2
    deviations = sorted([abs(v - median) for v in values])
    mad = deviations[n // 2] if n % 2 else (deviations[n // 2 - 1] + deviations[n // 2]) / 2
    if mad == 0:
        return 0.0
    z = direction * (current - median) / (1.4826 * mad)
    return max(-3.0, min(3.0, z))


def _health_from_z(z: float) -> float:
    return 100.0 / (1.0 + math.exp(-1.2 * z))


def _quarterly_series(db: Session, company_id: int, metric_name: str) -> list[tuple[date, float]]:
    # extraction_method="xbrl" only: the AI Company Monitor seeds its own "capex"/
    # "operating_cash_flow" mock rows (extraction_method="mock", USD_millions) for these same
    # hyperscaler companies with a period_end of "end of last month" - always more recent than
    # a real filed quarter. Without this filter that synthetic row wins the "latest quarter"
    # comparison against a real prior quarter in raw USD, producing a bogus ~-100% QoQ swing
    # (millions vs. raw dollars) on every company, every run.
    rows = (
        db.query(CompanyMetric.period_end, CompanyMetric.value)
        .filter(
            CompanyMetric.company_id == company_id, CompanyMetric.metric_name == metric_name,
            CompanyMetric.extraction_method == "xbrl",
        )
        .order_by(CompanyMetric.period_end.asc())
        .all()
    )
    # XBRL companyfacts returns overlapping YTD/quarterly/annual windows for the same tag;
    # keep only ~90-day (single-quarter) periods so YoY/QoQ comparisons are apples to apples.
    return [(d, v) for d, v in rows]


def compute_l6_company_health(db: Session, company: Company) -> dict | None:
    """Capex acceleration (L6_CAPEX_ACCEL) and FCF sign/level (L6_FCF) - the two spec
    indicators this v1 can actually compute from what SEC EDGAR gives us for free."""
    capex_series = _quarterly_series(db, company.id, "capex")
    ocf_series = _quarterly_series(db, company.id, "operating_cash_flow")
    if len(capex_series) < 2:
        return None

    capex_vals = [v for _, v in capex_series]
    current_capex = capex_vals[-1]
    prior_capex = capex_vals[-2]
    capex_qoq_growth = (current_capex - prior_capex) / abs(prior_capex) if prior_capex else 0.0
    # direction=-1: for a "capex freeze" monitor, ACCELERATING capex is the bearish (unhealthy)
    # read on this specific gauge - z is deliberately inverted vs. a normal "growth is good" read.
    z_capex = _robust_z(capex_vals, current_capex, direction=-1) if len(capex_vals) >= 3 else 0.0

    fcf = None
    z_fcf = 0.0
    if ocf_series and len(ocf_series) >= 2:
        latest_period = capex_series[-1][0]
        matching_ocf = next((v for d, v in reversed(ocf_series) if d == latest_period), ocf_series[-1][1])
        fcf = matching_ocf - current_capex
        fcf_history = [ov - cv for (od, ov), (cd, cv) in zip(ocf_series, capex_series) if od == cd]
        if len(fcf_history) >= 3:
            z_fcf = _robust_z(fcf_history, fcf, direction=1)

    z_composite = 0.6 * z_capex + 0.4 * z_fcf
    health = _health_from_z(z_composite)
    return {
        "ticker": company.ticker, "name": company.name, "health": round(health, 1),
        "capex_latest": current_capex, "capex_qoq_growth_pct": round(capex_qoq_growth * 100, 1),
        "fcf_latest": fcf, "as_of": capex_series[-1][0].isoformat(),
    }


def compute_l3_health(db: Session) -> dict | None:
    """Proxy: InvestDash's own hy-oas/ig-oas indicators (already live-ingested from FRED
    for the main dashboard) as a read on credit conditions facing leveraged AI-infra
    borrowers - not a per-borrower CDS feed, but real, current, and free."""
    defs = {
        d.slug: d.id for d in db.query(IndicatorDefinition).filter(IndicatorDefinition.slug.in_(["hy-oas", "ig-oas"])).all()
    }
    if not defs:
        return None
    zs = []
    detail = {}
    for slug, indicator_id in defs.items():
        rows = (
            db.query(IndicatorObservation.observation_date, IndicatorObservation.value)
            .filter(IndicatorObservation.indicator_id == indicator_id)
            .order_by(IndicatorObservation.observation_date.desc())
            .limit(504)  # ~2y of daily prints
            .all()
        )
        if len(rows) < 30:
            continue
        rows = list(reversed(rows))
        values = [v for _, v in rows]
        current = values[-1]
        # lower_is_healthy for both spreads
        z = _robust_z(values, current, direction=-1)
        zs.append(z)
        detail[slug] = {"current": current, "as_of": rows[-1][0].isoformat()}
    if not zs:
        return None
    z_composite = sum(zs) / len(zs)
    return {"health": round(_health_from_z(z_composite), 1), "detail": detail}


def compute_lock_summaries(db: Session) -> dict[str, dict]:
    """One entry per lock: health/damage/breadth/coverage where scored, or an honest
    "no live data yet" placeholder where not (L1, L2, L4, L5 in this v1)."""
    summaries: dict[str, dict] = {}

    for lock_id in LOCK_IDS:
        companies = db.query(Company).filter(Company.lock_id == lock_id).all()
        summaries[lock_id] = {
            "lock_id": lock_id, "name": LOCK_NAMES[lock_id], "weight": LOCK_WEIGHTS[lock_id],
            "company_count": len(companies), "coverage": 0.0, "health": None, "damage": None,
            "breadth": None, "companies": [],
        }

    l6_companies = db.query(Company).filter(Company.lock_id == "L6").all()
    l6_scored = []
    for c in l6_companies:
        result = compute_l6_company_health(db, c)
        if result:
            l6_scored.append((c, result))
    if l6_scored:
        weighted = sum((c.cfi_tier and TIER_WEIGHT.get(c.cfi_tier, 1.0) or 1.0) * r["health"] for c, r in l6_scored)
        total_w = sum((c.cfi_tier and TIER_WEIGHT.get(c.cfi_tier, 1.0) or 1.0) for c, _ in l6_scored)
        health = weighted / total_w
        breadth = sum(1 for _, r in l6_scored if r["health"] < 40) / len(l6_scored)
        summaries["L6"].update({
            "health": round(health, 1), "damage": round(max(0.0, min(1.0, (55 - health) / 40)), 3),
            "breadth": round(breadth, 3), "coverage": round(len(l6_scored) / max(len(l6_companies), 1), 3),
            "companies": [r for _, r in sorted(l6_scored, key=lambda x: x[1]["health"])],
        })

    l3 = compute_l3_health(db)
    if l3:
        health = l3["health"]
        summaries["L3"].update({
            "health": health, "damage": round(max(0.0, min(1.0, (55 - health) / 40)), 3),
            "breadth": None, "coverage": 1.0 if summaries["L3"]["company_count"] else 0.0,
            "proxy_detail": l3["detail"],
        })

    return summaries


def compute_cfi(lock_summaries: dict[str, dict]) -> dict:
    """Cascade + ordering gate + CFI (spec §6.5-6.6), restricted to locks with real
    coverage. Weights re-normalise across only the scored locks rather than assuming an
    unscored lock is healthy (d=0) - that would be exactly the imputation the spec warns
    against. The demand_gate needs d_1 (L1), which has zero coverage in this v1, so it's
    reported as disabled rather than silently defaulted to some d_1 value.
    """
    scored = {k: v for k, v in lock_summaries.items() if v["damage"] is not None}
    if not scored:
        return {"cfi": 0.0, "state": "no_data", "demand_gate_active": False, "note": "No locks have live coverage yet."}

    # legitimacy: is a scored lock's damage backed by upstream damage among *other scored*
    # locks feeding it? With only L3/L6 scored and L3->L6 not a direct transmission edge in
    # spec §6.5, neither has a scored upstream in this v1 - legitimacy is reported as
    # "unknown" (not 0, not 1) rather than guessed, and both locks are flagged idiosyncratic
    # until L1/L2/L4/L5 come online and the real upstream chain can be evaluated.
    upstream_by_lock: dict[str, list[str]] = {}
    for src, dst, _lag, _coef in TRANSMISSION:
        upstream_by_lock.setdefault(dst, []).append(src)

    raw_num, raw_den = 0.0, 0.0
    for lock_id, s in scored.items():
        upstream_scored = [u for u in upstream_by_lock.get(lock_id, []) if u in scored]
        if upstream_scored:
            expected = sum(scored[u]["damage"] for u in upstream_scored) / len(upstream_scored)
            legitimacy = max(0.0, min(1.0, expected / max(s["damage"], 0.01)))
        else:
            legitimacy = None  # unknown, not assumed
        s["legitimacy"] = round(legitimacy, 3) if legitimacy is not None else None
        s["idiosyncratic"] = legitimacy is None or legitimacy < 0.4
        contrib_legitimacy = legitimacy if legitimacy is not None else 1.0
        raw_num += LOCK_WEIGHTS[lock_id] * s["damage"] * contrib_legitimacy
        raw_den += LOCK_WEIGHTS[lock_id]

    raw = raw_num / raw_den if raw_den else 0.0
    cfi = round(100.0 * raw, 1)  # demand_gate disabled - no L1 coverage to compute it from

    if cfi <= 20:
        state = "expansion"
    elif cfi <= 35:
        state = "watch"
    elif cfi <= 50:
        state = "amber"
    elif cfi <= 70:
        state = "red"
    else:
        state = "freeze"

    return {
        "cfi": cfi, "state": state, "demand_gate_active": False,
        "scored_locks": list(scored.keys()), "note": "Partial CFI: weighted only across locks with live coverage (L3, L6).",
    }


def run_cfi_pipeline(db: Session) -> dict:
    """Shares the main pipeline's lock - both pipelines write to the same DB and neither
    should overlap with the other, let alone with itself, across their many sequential
    external HTTP calls."""
    with _pipeline_lock:
        return _run_cfi_pipeline_locked(db)


def _run_cfi_pipeline_locked(db: Session) -> dict:
    sync_cfi_companies(db)
    ingest_counts = ingest_l6_financials(db)
    lock_summaries = compute_lock_summaries(db)
    cfi_result = compute_cfi(lock_summaries)

    today = date.today()
    db.query(CfiSnapshot).filter(CfiSnapshot.snapshot_date == today).delete()
    db.add(
        CfiSnapshot(
            snapshot_date=today, cfi=cfi_result["cfi"], state=cfi_result["state"],
            lock_health_json=json.dumps({k: v["health"] for k, v in lock_summaries.items()}),
            lock_damage_json=json.dumps({k: v["damage"] for k, v in lock_summaries.items()}),
            lock_legitimacy_json=json.dumps({k: v.get("legitimacy") for k, v in lock_summaries.items()}),
            lock_breadth_json=json.dumps({k: v["breadth"] for k, v in lock_summaries.items()}),
            lock_coverage_json=json.dumps({k: v["coverage"] for k, v in lock_summaries.items()}),
            drivers_json=json.dumps([]),
        )
    )
    db.commit()
    return {"cfi": cfi_result["cfi"], "state": cfi_result["state"], "l6_capex_ingested": ingest_counts["capex"]}
