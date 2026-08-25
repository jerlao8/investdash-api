"""Tests for source_updated_today (observation as-of date in America/Los_Angeles)."""
from __future__ import annotations

from datetime import date, datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from app.api.routes.indicators import _source_updated_today

PT = ZoneInfo("America/Los_Angeles")


def test_true_when_observation_date_is_today():
    now = datetime(2026, 8, 25, 18, 0, tzinfo=PT)
    obs = SimpleNamespace(observation_date=date(2026, 8, 25))
    assert _source_updated_today(obs, now) is True


def test_false_when_observation_date_is_yesterday():
    now = datetime(2026, 8, 25, 10, 0, tzinfo=PT)
    # Daily series often lag one session; quarterly as-of is never "today" mid-quarter.
    obs = SimpleNamespace(observation_date=date(2026, 8, 24))
    assert _source_updated_today(obs, now) is False


def test_false_for_quarterly_as_of_even_if_pulled_today():
    now = datetime(2026, 8, 25, 10, 0, tzinfo=PT)
    obs = SimpleNamespace(observation_date=date(2026, 6, 30))
    assert _source_updated_today(obs, now) is False


def test_false_when_missing():
    assert _source_updated_today(None) is False
