"""Unit tests for wake-up catch-up schedule detection."""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from app.jobs.scheduler import most_recent_due_job, should_run_catchup

PT = ZoneInfo("America/Los_Angeles")


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
