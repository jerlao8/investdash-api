"""APScheduler wiring (PRD Section 47).

The real cadence differences (daily 04:00 PT macro pulls vs. weekly FINRA/CFTC vs. monthly
CPI/semis) mostly don't matter for this connector layer, since every connector's fetch()
call is idempotent (re-fetches full available history, only new observation_dates get
inserted - see jobs/pipeline.py). So all three schedules below simply call the same
run_full_pipeline(); splitting them out preserves the PRD's job structure and makes it easy
to later give each cadence connector-specific logic without touching orchestration code.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy.orm import Session

from app.db.models import MarketSnapshot
from app.db.session import SessionLocal
from app.jobs.cfi_pipeline import run_cfi_pipeline
from app.jobs.pipeline import run_full_pipeline

logger = logging.getLogger("investdash.scheduler")

TZ_NAME = "America/Los_Angeles"

# Shared schedule definitions — used by the live scheduler and wake-up catch-up.
SCHEDULED_JOBS: list[tuple[str, CronTrigger]] = [
    ("daily_04_pt", CronTrigger(hour=4, minute=0, timezone=TZ_NAME)),
    ("post_close", CronTrigger(hour=13, minute=15, timezone=TZ_NAME)),
    ("weekly", CronTrigger(day_of_week="sat", hour=6, minute=0, timezone=TZ_NAME)),
    ("monthly", CronTrigger(day=1, hour=7, minute=0, timezone=TZ_NAME)),
]


def _prev_fire_time(trigger: CronTrigger, now: datetime) -> datetime | None:
    """Most recent fire time of `trigger` that is <= now (timezone-aware)."""
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    cursor = now - timedelta(days=45)
    prev: datetime | None = None
    # Walk forward from a safe past point until we pass `now`.
    while True:
        nxt = trigger.get_next_fire_time(prev, cursor)
        if nxt is None or nxt > now:
            return prev
        prev = nxt
        cursor = nxt + timedelta(microseconds=1)


def most_recent_due_job(now: datetime | None = None) -> tuple[str, datetime] | None:
    """Return (job_name, fire_at) for the latest scheduled slot that should already have run."""
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    best: tuple[str, datetime] | None = None
    for name, trigger in SCHEDULED_JOBS:
        prev = _prev_fire_time(trigger, now)
        if prev is None:
            continue
        if best is None or prev > best[1]:
            best = (name, prev)
    return best


def _as_aware_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def should_run_catchup(
    last_run: datetime | None,
    now: datetime | None = None,
) -> tuple[bool, str | None, datetime | None]:
    """If the latest scheduled job was missed (e.g. host was asleep), return (True, job, fire_at)."""
    now = now or datetime.now(timezone.utc)
    due = most_recent_due_job(now)
    if due is None:
        return False, None, None
    name, fire_at = due
    if last_run is None:
        return True, name, fire_at
    if _as_aware_utc(last_run) < _as_aware_utc(fire_at):
        return True, name, fire_at
    return False, None, None


def last_pipeline_run_at(db: Session) -> datetime | None:
    snap = db.query(MarketSnapshot).order_by(MarketSnapshot.created_at.desc()).first()
    return snap.created_at if snap else None


def daily_observations_lag_today(db: Session) -> bool:
    """True when no daily series has an observation dated America/Los_Angeles today.

    Schedule-based catch-up can skip incorrectly if MarketSnapshot.created_at looks fresh
    (e.g. backfill rows) while mock/live series never advanced to today_pt — common after
    Render free-tier sleep. Observation lag is the ground truth that the dashboard is stale.
    """
    from sqlalchemy import func

    from app.db.models import IndicatorDefinition, IndicatorObservation
    from app.timeutil import today_pt

    latest = (
        db.query(func.max(IndicatorObservation.observation_date))
        .join(IndicatorDefinition, IndicatorDefinition.id == IndicatorObservation.indicator_id)
        .filter(
            IndicatorDefinition.active == True,  # noqa: E712
            IndicatorDefinition.frequency == "daily",
        )
        .scalar()
    )
    if latest is None:
        return True
    return latest < today_pt()


def _company_roster_incomplete(db: Session) -> bool:
    """True when the seed list (app/seed/companies.py) has a ticker not yet in the companies
    table - e.g. right after a deploy that added new companies. Without this, seed_and_sync's
    upsert only runs when the main indicator pipeline's OWN freshness check decides a run is
    needed, so a newly-added company can sit missing from the API for hours after its fix
    ships, just because daily macro observations already looked current."""
    from app.db.models import Company
    from app.seed.companies import COMPANIES

    existing = {c.ticker for c in db.query(Company.ticker).all()}
    return any(c["ticker"] not in existing for c in COMPANIES)


def _cfi_catchup_needed(db: Session) -> bool:
    """True when the Capex Freeze Monitor has no snapshot for today yet - checked
    independently of whatever the main indicator pipeline decides. The two pipelines track
    unrelated freshness concepts (daily macro observations vs. quarterly company financials),
    so gating CFI entirely behind the main pipeline's own "needed" decision meant CFI could
    stay stale (or, before it was wired in at all, never run) even on a run where the main
    dashboard already looked current and wake catch-up correctly skipped it."""
    from app.db.models import CfiSnapshot
    from app.timeutil import today_pt

    latest = db.query(CfiSnapshot).order_by(CfiSnapshot.snapshot_date.desc()).first()
    return latest is None or latest.snapshot_date < today_pt()


def run_catchup_if_needed() -> dict | None:
    """On process wake: run the pipeline if a cron slot was missed, daily data lags PT today,
    the company roster is missing a seeded ticker, or the Capex Freeze Monitor hasn't produced
    today's snapshot - each checked independently so one sub-system looking fresh can't mask
    another one being stale or never-yet-run."""
    db = SessionLocal()
    try:
        last_run = last_pipeline_run_at(db)
        needed, job_name, fire_at = should_run_catchup(last_run)
        if not needed and daily_observations_lag_today(db):
            needed, job_name, fire_at = True, "stale_daily_observations", None
        if not needed and _company_roster_incomplete(db):
            needed, job_name, fire_at = True, "company_roster_incomplete", None

        cfi_needed = _cfi_catchup_needed(db)

        if not needed and not cfi_needed:
            logger.info(
                "wake catch-up skipped (last_run=%s, no missed schedule, daily obs current)",
                last_run,
            )
            return None

        result = None
        if needed:
            logger.info(
                "wake catch-up running %s (due=%s, last_run=%s)",
                job_name,
                fire_at,
                last_run,
            )
            result = run_full_pipeline(db)
            logger.info("wake catch-up completed: %s", result)
        if cfi_needed:
            _run_cfi_pipeline_safely(db)
        return result
    except Exception:  # noqa: BLE001
        logger.exception("wake catch-up failed")
        db.rollback()
        return None
    finally:
        db.close()


def _run_cfi_pipeline_safely(db: Session) -> None:
    """The Capex Freeze Monitor has no scheduling of its own (its pipeline previously only
    ran from a manual, unwired admin endpoint - the companies/L6-financials tables never
    synced in production, so /api/cfi/overview stayed permanently empty). Piggyback it on
    the same cadence as the main pipeline; isolated try/except so an SEC EDGAR hiccup here
    (ingest_l6_financials has no mock fallback) can't take down the main dashboard's run."""
    try:
        cfi_result = run_cfi_pipeline(db)
        logger.info("cfi pipeline completed: %s", cfi_result)
    except Exception:  # noqa: BLE001
        logger.exception("cfi pipeline failed")
        db.rollback()


def _run_pipeline_job(job_name: str) -> None:
    db = SessionLocal()
    try:
        result = run_full_pipeline(db)
        logger.info("scheduled job %s completed: %s", job_name, result)
        _run_cfi_pipeline_safely(db)
    except Exception:  # noqa: BLE001
        logger.exception("scheduled job %s failed", job_name)
        db.rollback()
    finally:
        db.close()


def create_scheduler() -> BackgroundScheduler:
    scheduler = BackgroundScheduler(timezone=TZ_NAME)
    for job_name, trigger in SCHEDULED_JOBS:
        scheduler.add_job(
            _run_pipeline_job,
            trigger,
            args=[job_name],
            id=job_name,
            replace_existing=True,
        )
    return scheduler
