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

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.db.session import SessionLocal
from app.jobs.pipeline import run_full_pipeline

logger = logging.getLogger("investdash.scheduler")


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
    scheduler = BackgroundScheduler(timezone="America/Los_Angeles")
    # Daily 04:00 PT: macro/liquidity sources + prior day's equity prices + scores + alerts + feed.
    scheduler.add_job(_run_pipeline_job, CronTrigger(hour=4, minute=0), args=["daily_04_pt"], id="daily_04_pt", replace_existing=True)
    # After major market close (~13:15 PT / 16:15 ET): VIX/options stats + prices + fast indicators.
    scheduler.add_job(_run_pipeline_job, CronTrigger(hour=13, minute=15), args=["post_close"], id="post_close", replace_existing=True)
    # Weekly: FINRA margin, CFTC positioning, H.8 banking, source integrity, global refresh.
    scheduler.add_job(_run_pipeline_job, CronTrigger(day_of_week="sat", hour=6, minute=0), args=["weekly"], id="weekly", replace_existing=True)
    # Monthly: CPI/PCE, semiconductor sales, global PMIs, credit growth, banking, AI company updates.
    scheduler.add_job(_run_pipeline_job, CronTrigger(day=1, hour=7, minute=0), args=["monthly"], id="monthly", replace_existing=True)
    return scheduler
