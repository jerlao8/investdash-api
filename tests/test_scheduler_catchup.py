"""Unit tests for wake-up catch-up schedule detection."""
from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.models import CfiSnapshot, Company
from app.db.session import Base
from app.jobs.scheduler import _cfi_catchup_needed, _company_roster_incomplete, most_recent_due_job, should_run_catchup
from app.seed.companies import COMPANIES
from app.timeutil import today_pt

PT = ZoneInfo("America/Los_Angeles")


def _make_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine, tables=[Company.__table__, CfiSnapshot.__table__])
    return sessionmaker(bind=engine)()


def test_company_roster_incomplete_when_a_seeded_ticker_is_missing():
    db = _make_session()
    # Seed every ticker except one, mirroring a deploy that just added a new company.
    for c in COMPANIES[:-1]:
        db.add(Company(name=c["name"], ticker=c["ticker"], sector=c["sector"], subsector=c["subsector"], tier=c["tier"], active=True))
    db.commit()
    assert _company_roster_incomplete(db) is True


def test_company_roster_complete_when_every_seeded_ticker_present():
    db = _make_session()
    for c in COMPANIES:
        db.add(Company(name=c["name"], ticker=c["ticker"], sector=c["sector"], subsector=c["subsector"], tier=c["tier"], active=True))
    db.commit()
    assert _company_roster_incomplete(db) is False


def test_cfi_catchup_needed_when_no_snapshot_ever_ran():
    db = _make_session()
    assert _cfi_catchup_needed(db) is True


def test_cfi_catchup_needed_when_latest_snapshot_is_from_a_prior_day():
    db = _make_session()
    db.add(CfiSnapshot(
        snapshot_date=today_pt() - timedelta(days=1), cfi=10.0, state="expansion",
        lock_health_json="{}", lock_damage_json="{}", lock_legitimacy_json="{}",
        lock_breadth_json="{}", lock_coverage_json="{}",
    ))
    db.commit()
    assert _cfi_catchup_needed(db) is True


def test_cfi_catchup_not_needed_when_todays_snapshot_already_exists():
    db = _make_session()
    db.add(CfiSnapshot(
        snapshot_date=today_pt(), cfi=10.0, state="expansion",
        lock_health_json="{}", lock_damage_json="{}", lock_legitimacy_json="{}",
        lock_breadth_json="{}", lock_coverage_json="{}",
    ))
    db.commit()
    assert _cfi_catchup_needed(db) is False


def test_most_recent_due_after_morning_job():
    # Tuesday 10:00 PT — latest due is today's 04:00 daily job.
    now = datetime(2026, 8, 25, 10, 0, tzinfo=PT)
    name, fire_at = most_recent_due_job(now)
    assert name == "daily_04_pt"
    assert fire_at == datetime(2026, 8, 25, 4, 0, tzinfo=PT)


def test_most_recent_due_after_post_close():
    now = datetime(2026, 8, 25, 15, 0, tzinfo=PT)
    name, fire_at = most_recent_due_job(now)
    assert name == "post_close"
    assert fire_at == datetime(2026, 8, 25, 13, 15, tzinfo=PT)


def test_catchup_needed_when_last_run_before_due():
    now = datetime(2026, 8, 25, 10, 0, tzinfo=PT)
    last_run = datetime(2026, 8, 24, 13, 20, tzinfo=PT)  # yesterday's post_close
    needed, job, fire_at = should_run_catchup(last_run, now)
    assert needed is True
    assert job == "daily_04_pt"
    assert fire_at == datetime(2026, 8, 25, 4, 0, tzinfo=PT)


def test_catchup_skipped_when_already_ran():
    now = datetime(2026, 8, 25, 10, 0, tzinfo=PT)
    last_run = datetime(2026, 8, 25, 4, 5, tzinfo=PT)
    needed, job, fire_at = should_run_catchup(last_run, now)
    assert needed is False
    assert job is None
    assert fire_at is None


def test_catchup_needed_when_never_ran():
    now = datetime(2026, 8, 25, 10, 0, tzinfo=PT)
    needed, job, _ = should_run_catchup(None, now)
    assert needed is True
    assert job == "daily_04_pt"
