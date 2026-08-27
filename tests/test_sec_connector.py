from datetime import date

from app.connectors.base import RawObservation
from app.connectors.sec import SecConnector


def _facts_payload(tag: str, entries: list[dict]) -> dict:
    return {"facts": {"us-gaap": {tag: {"units": {"USD": entries}}}}}


def _entry(start: str, end: str, val: float, form: str = "10-Q", filed: str = "2026-01-01") -> dict:
    return {"start": start, "end": end, "val": val, "form": form, "filed": filed}


def test_normalize_passes_through_a_lone_discrete_quarter():
    """A company that files a genuinely discrete (~91 day) quarter with no cumulative
    siblings should have that value used as-is."""
    payload = _facts_payload("Capex", [_entry("2025-04-01", "2025-06-30", 100.0)])
    raw = RawObservation(series_identifier="0000000001:Capex", payload=payload, source_url="https://example.com")
    out = SecConnector().normalize(raw)
    assert len(out) == 1
    assert out[0].observation_date == date(2025, 6, 30)
    assert out[0].value == 100.0


def test_normalize_diffs_a_year_to_date_cumulative_ladder():
    """Cash-flow-statement concepts are commonly filed as cumulative-since-fiscal-year-start:
    Q1 alone, Q1+Q2, Q1+Q2+Q3, then the full year via the 10-K. Discrete quarters must be
    recovered by diffing consecutive entries, not by reading each "val" as its own quarter."""
    payload = _facts_payload(
        "Capex",
        [
            _entry("2025-01-01", "2025-03-31", 10.0),   # Q1
            _entry("2025-01-01", "2025-06-30", 25.0),   # Q1+Q2 YTD
            _entry("2025-01-01", "2025-09-30", 45.0),   # Q1+Q2+Q3 YTD
            _entry("2025-01-01", "2025-12-31", 70.0, form="10-K"),  # full year
        ],
    )
    raw = RawObservation(series_identifier="0000000001:Capex", payload=payload, source_url="https://example.com")
    out = SecConnector().normalize(raw)
    values_by_end = {o.observation_date: o.value for o in out}
    assert values_by_end[date(2025, 3, 31)] == 10.0
    assert values_by_end[date(2025, 6, 30)] == 15.0
    assert values_by_end[date(2025, 9, 30)] == 20.0
    assert values_by_end[date(2025, 12, 31)] == 25.0


def test_normalize_drops_trailing_twelve_month_comparative_facts():
    """A trailing-twelve-month comparative fact spans exactly 4 quarters back, so its "start"
    always lands exactly on some real quarter's own discrete-start date - e.g. a TTM ending
    2026-06-30 starts 2025-07-01, the same start as the real, discrete Q3 2025 quarter. That
    collision must not be mistaken for a genuine cumulative ladder (which always has a true
    ~182 or ~273 day rung); the TTM fact should be dropped and the real discrete quarter kept."""
    payload = _facts_payload(
        "Capex",
        [
            _entry("2025-07-01", "2025-09-30", 35.0),     # real, discrete Q3 2025
            _entry("2025-07-01", "2026-06-30", 173.0),    # bogus TTM-through-Q2-2026, same start
        ],
    )
    raw = RawObservation(series_identifier="0000000001:Capex", payload=payload, source_url="https://example.com")
    out = SecConnector().normalize(raw)
    assert len(out) == 1
    assert out[0].observation_date == date(2025, 9, 30)
    assert out[0].value == 35.0


def test_normalize_dedupes_refiled_periods_keeping_latest_filing():
    """The same (start, end) period is often re-reported as a prior-year comparative in a
    later filing - keep only the latest filing's value, not a duplicate row."""
    payload = _facts_payload(
        "Capex",
        [
            _entry("2025-04-01", "2025-06-30", 100.0, filed="2025-08-01"),
            _entry("2025-04-01", "2025-06-30", 100.0, filed="2026-08-01"),
        ],
    )
    raw = RawObservation(series_identifier="0000000001:Capex", payload=payload, source_url="https://example.com")
    out = SecConnector().normalize(raw)
    assert len(out) == 1


def test_normalize_skips_non_10q_10k_forms():
    payload = _facts_payload("Capex", [_entry("2025-04-01", "2025-06-30", 100.0, form="8-K")])
    raw = RawObservation(series_identifier="0000000001:Capex", payload=payload, source_url="https://example.com")
    out = SecConnector().normalize(raw)
    assert out == []
