from datetime import date

from app.connectors.base import RawObservation
from app.connectors.cboe import CboeConnector


def test_normalize_ohlc_csv_uses_close_column():
    """VIX/VIX9D-style CSVs: DATE,OPEN,HIGH,LOW,CLOSE."""
    csv_text = "DATE,OPEN,HIGH,LOW,CLOSE\n01/02/2026,15.0,16.0,14.5,15.5\n"
    raw = RawObservation(series_identifier="VIX", payload={"csv_text": csv_text}, source_url="https://example.com")
    out = CboeConnector().normalize(raw)
    assert len(out) == 1
    assert out[0].observation_date == date(2026, 1, 2)
    assert out[0].value == 15.5


def test_normalize_single_value_csv_uses_series_name_column():
    """VVIX/SKEW-style CSVs: DATE,VVIX (no CLOSE column at all) - regression test for the
    bug where every row was silently skipped because the connector only looked for CLOSE."""
    csv_text = "DATE,VVIX\n03/06/2026,71.73\n03/15/2026,15.71\n"
    raw = RawObservation(series_identifier="VVIX", payload={"csv_text": csv_text}, source_url="https://example.com")
    out = CboeConnector().normalize(raw)
    assert len(out) == 2
    assert out[0].observation_date == date(2026, 3, 6)
    assert out[0].value == 71.73
    assert out[1].value == 15.71
