"""today_pt() must follow America/Los_Angeles, not the host UTC calendar day."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from app.timeutil import today_pt

PT = ZoneInfo("America/Los_Angeles")


def test_today_pt_evening_before_utc_midnight_is_still_prior_calendar_day():
    # 2026-08-25 05:00 UTC == 2026-08-24 22:00 PT
    now = datetime(2026, 8, 25, 5, 0, tzinfo=ZoneInfo("UTC"))
    assert today_pt(now).isoformat() == "2026-08-24"


def test_today_pt_afternoon_pt_matches_calendar_day():
    now = datetime(2026, 8, 24, 15, 0, tzinfo=PT)
    assert today_pt(now).isoformat() == "2026-08-24"
