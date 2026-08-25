"""Cboe volatility-index connector (VIX, VIX9D, VVIX, ...).

Live mode pulls Cboe's public historical-prices CSV for the given index. Falls back to
synthetic mock on failure.
"""

from __future__ import annotations

import csv
import io
from datetime import date, timedelta

from app.connectors.base import BaseConnector, Observation, RawObservation, http_get_with_retry, is_proxy_series
from app.connectors.synthetic import MockParams, backfill_series
from app.timeutil import today_pt

CBOE_CSV_URL = "https://cdn.cboe.com/api/global/us_indices/daily_prices/{index}_History.csv"


class CboeConnector(BaseConnector):
    name = "Cboe"
    fixture_dir = "cboe"

    def fetch(
        self,
        series_identifier: str,
        mock_params: MockParams | None = None,
        years: int = 12,
        frequency: str = "daily",
    ) -> RawObservation:
        if self.mode == "live" and not is_proxy_series(series_identifier):
            try:
                return self._fetch_live(series_identifier)
            except Exception as exc:  # noqa: BLE001
                self._last_error = f"live fetch failed for {series_identifier}: {exc}"
        return self._fetch_mock(
            series_identifier,
            mock_params or MockParams(base=18.0, vol=1.5, floor=8.0),
            years,
            frequency=frequency,
        )

    def _fetch_live(self, series_identifier: str) -> RawObservation:
        url = CBOE_CSV_URL.format(index=series_identifier.upper())
        resp = http_get_with_retry(url)
        self._last_error = None
        return RawObservation(
            series_identifier=series_identifier,
            payload={"csv_text": resp.text},
            source_url=url,
        )

    def _fetch_mock(
        self, series_identifier: str, params: MockParams, years: int, frequency: str = "daily"
    ) -> RawObservation:
        end = today_pt()
        start = end - timedelta(days=365 * years)
        points = backfill_series(series_identifier, frequency, params, start, end)
        payload = {"observations": [{"date": d.isoformat(), "value": v} for d, v in points]}
        return RawObservation(series_identifier=series_identifier, payload=payload, source_url="https://www.cboe.com/")

    def normalize(self, raw: RawObservation) -> list[Observation]:
        if "csv_text" in raw.payload:
            reader = csv.DictReader(io.StringIO(raw.payload["csv_text"]))
            out = []
            for row in reader:
                d_str = row.get("DATE") or row.get("Date")
                v_str = row.get("CLOSE") or row.get("Close")
                if v_str is None:
                    # Single-value index CSVs (e.g. VVIX, SKEW: "DATE,VVIX") use the series
                    # name itself as the value column header instead of CLOSE, unlike the
                    # OHLC series (VIX, VIX9D: "DATE,OPEN,HIGH,LOW,CLOSE") - fall back to
                    # whichever column isn't the date.
                    for key, val in row.items():
                        if key and key.strip().upper() != "DATE":
                            v_str = val
                            break
                if not d_str or not v_str:
                    continue
                try:
                    d = date.fromisoformat(_normalize_date(d_str))
                    v = float(v_str)
                except ValueError:
                    continue
                out.append(Observation(observation_date=d, value=v, source_url=raw.source_url))
            return out
        out = []
        for row in raw.payload.get("observations", []):
            out.append(
                Observation(observation_date=date.fromisoformat(row["date"]), value=float(row["value"]), source_url=raw.source_url)
            )
        return out


def _normalize_date(s: str) -> str:
    if "/" in s:
        m, d, y = s.split("/")
        return f"{y}-{int(m):02d}-{int(d):02d}"
    return s
