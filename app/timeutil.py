"""Dashboard calendar helpers.

Market/ops semantics (staleness, "updated today", cron slots, mock series end dates) use
America/Los_Angeles. Render and most containers run in UTC, so plain date.today() drifts a
day ahead of PT after 17:00 PT / 00:00 UTC.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

PT = ZoneInfo("America/Los_Angeles")


def today_pt(now: datetime | None = None) -> date:
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return now.astimezone(PT).date()
