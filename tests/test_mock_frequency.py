"""Mock backfill should respect each indicator's real frequency."""
from __future__ import annotations

from datetime import date

from app.connectors.synthetic import MockParams, backfill_series, normalize_frequency


def test_normalize_frequency():
    assert normalize_frequency("monthly") == "monthly"
    assert normalize_frequency("Daily") == "daily"
    assert normalize_frequency("nope") == "daily"


def test_monthly_backfill_is_sparse_vs_daily():
    params = MockParams(base=5.0, vol=0.01)
    start, end = date(2024, 1, 1), date(2024, 12, 31)
    daily = backfill_series("unemployment-rate", "daily", params, start, end)
    monthly = backfill_series("unemployment-rate", "monthly", params, start, end)
    assert len(daily) > 300
    assert 10 <= len(monthly) <= 14
