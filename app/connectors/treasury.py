"""U.S. Treasury daily par-yield-curve connector.

Live mode pulls the official daily treasury par yield curve CSV
(home.treasury.gov) for the current year and extracts the requested tenor
column (series_identifier is a tenor label such as "10 Yr", "2 Yr", "3 Mo").
Falls back to a synthetic mock series on any failure.
"""

from __future__ import annotations

import csv
import io
from datetime import date, timedelta

from app.connectors.base import BaseConnector, Observation, RawObservation, http_get_with_retry, is_proxy_series
from app.connectors.synthetic import MockParams, backfill_series

TREASURY_CSV_URL = (
    "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/"
    "daily-treasury-rates.csv/{year}/all"
)


class TreasuryConnector(BaseConnector):
    name = "U.S. Treasury"
    fixture_dir = "treasury"

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
            mock_params or MockParams(base=4.0, vol=0.04),
            years,
            frequency=frequency,
        )

    def _fetch_live(self, series_identifier: str) -> RawObservation:
        url = TREASURY_CSV_URL.format(year=date.today().year)
        resp = http_get_with_retry(
            url, params={"type": "daily_treasury_yield_curve", "field_tdr_date_value": date.today().year, "page": "", "_format": "csv"}
        )
        self._last_error = None
        return RawObservation(
            series_identifier=series_identifier,
            payload={"csv_text": resp.text},
            source_url="https://home.treasury.gov/resource-center/data-chart-center/interest-rates/",
        )

    def _fetch_mock(
        self, series_identifier: str, params: MockParams, years: int, frequency: str = "daily"
    ) -> RawObservation:
        end = date.today()
        start = end - timedelta(days=365 * years)
        points = backfill_series(series_identifier, frequency, params, start, end)
        payload = {"observations": [{"date": d.isoformat(), "value": v} for d, v in points]}
        return RawObservation(
            series_identifier=series_identifier,
            payload=payload,
            source_url="https://home.treasury.gov/resource-center/data-chart-center/interest-rates/",
        )

    def normalize(self, raw: RawObservation) -> list[Observation]:
        if "csv_text" in raw.payload:
            return self._normalize_csv(raw)
        out = []
        for row in raw.payload.get("observations", []):
            out.append(
                Observation(
                    observation_date=date.fromisoformat(row["date"]),
                    value=float(row["value"]),
                    source_url=raw.source_url,
                )
            )
        return out

    def _normalize_csv(self, raw: RawObservation) -> list[Observation]:
        reader = csv.DictReader(io.StringIO(raw.payload["csv_text"]))
        tenor_col = raw.series_identifier
        out: list[Observation] = []
        for row in reader:
            date_str = row.get("Date")
            val_str = row.get(tenor_col)
            if not date_str or not val_str:
                continue
            try:
                d = date.fromisoformat(_mmddyyyy_to_iso(date_str))
                v = float(val_str)
            except ValueError:
                continue
            out.append(Observation(observation_date=d, value=v, source_url=raw.source_url))
        return out


def _mmddyyyy_to_iso(s: str) -> str:
    if "/" in s:
        m, d, y = s.split("/")
        return f"{y}-{int(m):02d}-{int(d):02d}"
    return s
