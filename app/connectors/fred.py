"""FRED / ALFRED connector.

Live mode calls the real FRED API (requires FRED_API_KEY). Mock mode (or any live-call
failure, which falls back automatically) generates a deterministic synthetic series shaped
like a FRED `observations` response so `normalize()` is identical either way.
"""

from __future__ import annotations

from datetime import date, timedelta

from app.connectors.base import BaseConnector, Observation, RawObservation, http_get_with_retry, is_proxy_series
from app.connectors.synthetic import MockParams, backfill_series

FRED_BASE_URL = "https://api.stlouisfed.org/fred/series/observations"


class FredConnector(BaseConnector):
    name = "FRED/ALFRED"
    fixture_dir = "fred"

    def fetch(
        self, series_identifier: str, mock_params: MockParams | None = None, years: int = 12
    ) -> RawObservation:
        if self.mode == "live" and self.settings.fred_api_key and not is_proxy_series(series_identifier):
            try:
                return self._fetch_live(series_identifier)
            except Exception as exc:  # noqa: BLE001
                self._last_error = f"live fetch failed for {series_identifier}: {exc}"
        return self._fetch_mock(series_identifier, mock_params or MockParams(base=1.0, vol=0.05), years)

    def _fetch_live(self, series_identifier: str) -> RawObservation:
        params = {
            "series_id": series_identifier,
            "api_key": self.settings.fred_api_key,
            "file_type": "json",
        }
        resp = http_get_with_retry(FRED_BASE_URL, params=params)
        data = resp.json()
        self._last_error = None
        return RawObservation(
            series_identifier=series_identifier,
            payload=data,
            source_url=f"https://fred.stlouisfed.org/series/{series_identifier}",
        )

    def _fetch_mock(self, series_identifier: str, params: MockParams, years: int) -> RawObservation:
        end = date.today()
        start = end - timedelta(days=365 * years)
        points = backfill_series(series_identifier, "daily", params, start, end)
        payload = {
            "observations": [
                {"date": d.isoformat(), "value": str(v)} for d, v in points
            ]
        }
        return RawObservation(
            series_identifier=series_identifier,
            payload=payload,
            source_url=f"https://fred.stlouisfed.org/series/{series_identifier}",
        )

    def normalize(self, raw: RawObservation) -> list[Observation]:
        out: list[Observation] = []
        for row in raw.payload.get("observations", []):
            val = row.get("value")
            if val in (None, ".", ""):
                continue
            try:
                fval = float(val)
            except ValueError:
                continue
            out.append(
                Observation(
                    observation_date=date.fromisoformat(row["date"]),
                    value=fval,
                    source_url=raw.source_url,
                )
            )
        return out
