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


def run_catchup_if_needed() -> dict | None:
    """On process wake: run the pipeline if a cron slot was missed or daily data lags PT today."""
    db = SessionLocal()
    try:
        last_run = last_pipeline_run_at(db)
        needed, job_name, fire_at = should_run_catchup(last_run)
        if not needed and daily_observations_lag_today(db):
            needed, job_name, fire_at = True, "stale_daily_observations", None
        if not needed:
            logger.info(
                "wake catch-up skipped (last_run=%s, no missed schedule, daily obs current)",
                last_run,
            )
            return None
        logger.info(
            "wake catch-up running %s (due=%s, last_run=%s)",
            job_name,
            fire_at,
            last_run,
        )
        result = run_full_pipeline(db)
        logger.info("wake catch-up completed: %s", result)
        return result
    except Exception:  # noqa: BLE001
        logger.exception("wake catch-up failed")
        db.rollback()
        return None
    finally:
        db.close()


def _run_pipeline_job(job_name: str) -> None:
    db = SessionLocal()
    try:
        result = run_full_pipeline(db)
        logger.info("scheduled job %s completed: %s", job_name, result)
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
