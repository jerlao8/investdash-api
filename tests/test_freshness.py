from datetime import date

from app.jobs.pipeline import FRESHNESS_DAYS, _business_day_gap


def test_friday_to_monday_is_not_stale():
    # Markets were closed Sat/Sun - Friday's data is still the correct "latest" on Monday.
    gap = _business_day_gap(date(2026, 8, 21), date(2026, 8, 24))  # Fri -> Mon
    assert gap <= FRESHNESS_DAYS["daily"]


def test_friday_to_sunday_is_not_stale():
    gap = _business_day_gap(date(2026, 8, 21), date(2026, 8, 23))  # Fri -> Sun
    assert gap <= FRESHNESS_DAYS["daily"]


def test_same_day_has_zero_gap():
    assert _business_day_gap(date(2026, 8, 24), date(2026, 8, 24)) == 0.0


def test_genuine_multi_business_day_lapse_is_still_stale():
    # No update all week (Fri -> the following Thursday) is a real problem, weekend or not.
    gap = _business_day_gap(date(2026, 8, 21), date(2026, 8, 27))  # Fri -> following Thu
    assert gap > FRESHNESS_DAYS["daily"]


def test_gap_is_never_negative():
    assert _business_day_gap(date(2026, 8, 24), date(2026, 8, 20)) == 0.0
