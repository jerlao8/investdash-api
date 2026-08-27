"""Mock backfill should respect each indicator's real frequency."""
from __future__ import annotations

from datetime import date, timedelta

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


def test_sliding_end_appends_new_terminal_value():
    """Regression: end=today used to slide start with it and reuse the same terminal value."""
    params = MockParams(base=5.0, vol=0.2)
    end_a = date(2026, 8, 25)
    end_b = date(2026, 8, 26)
    start_a = end_a - timedelta(days=365 * 12)
    start_b = end_b - timedelta(days=365 * 12)
    series_a = backfill_series("hy-oas", "daily", params, start_a, end_a)
    series_b = backfill_series("hy-oas", "daily", params, start_b, end_b)
    assert series_a[-1][0] == end_a
    assert series_b[-1][0] == end_b
    assert series_a[-1][1] != series_b[-1][1]
    # Shared dates keep stable values across runs.
    by_a = dict(series_a)
    by_b = dict(series_b)
    shared = set(by_a) & set(by_b)
    assert len(shared) > 1000
    for d in list(shared)[:50]:
        assert by_a[d] == by_b[d]
