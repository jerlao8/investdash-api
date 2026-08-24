"""New York Fed reference-rates connector (SOFR / TGCR / BGCR).

Live mode calls the public NY Fed markets API (no key required). series_identifier is the
rate type: "sofr", "tgcr", or "bgcr". Falls back to synthetic mock on failure.
"""

from __future__ import annotations

from datetime import date, timedelta

from app.connectors.base import BaseConnector, Observation, RawObservation, http_get_with_retry, is_proxy_series
from app.connectors.synthetic import MockParams, backfill_series

NYFED_URL = "https://markets.newyorkfed.org/api/rates/secured/{rate_type}/search.json"


class NYFedConnector(BaseConnector):
    name = "New York Fed"
    fixture_dir = "nyfed"

    def fetch(
        self, series_identifier: str, mock_params: MockParams | None = None, years: int = 12
    ) -> RawObservation:
        if self.mode == "live" and not is_proxy_series(series_identifier):
            try:
                return self._fetch_live(series_identifier)
            except Exception as exc:  # noqa: BLE001
                self._last_error = f"live fetch failed for {series_identifier}: {exc}"
        return self._fetch_mock(series_identifier, mock_params or MockParams(base=5.0, vol=0.03), years)

    def _fetch_live(self, series_identifier: str) -> RawObservation:
        end = date.today()
        start = end - timedelta(days=365 * 3)  # NY Fed API history is more limited than FRED
        url = NYFED_URL.format(rate_type=series_identifier.lower())
        resp = http_get_with_retry(
            url, params={"startDate": start.isoformat(), "endDate": end.isoformat()}
        )
        self._last_error = None
        return RawObservation(
            series_identifier=series_identifier,
            payload=resp.json(),
            source_url="https://markets.newyorkfed.org/",
        )

    def _fetch_mock(self, series_identifier: str, params: MockParams, years: int) -> RawObservation:
        end = date.today()
        start = end - timedelta(days=365 * years)
        points = backfill_series(series_identifier, "daily", params, start, end)
        payload = {"refRates": [{"effectiveDate": d.isoformat(), "percentRate": v} for d, v in points]}
        return RawObservation(
            series_identifier=series_identifier,
            payload=payload,
            source_url="https://markets.newyorkfed.org/",
        )

    def normalize(self, raw: RawObservation) -> list[Observation]:
        rows = raw.payload.get("refRates", [])
        out = []
        for row in rows:
            d = row.get("effectiveDate")
            v = row.get("percentRate")
            if d is None or v is None:
                continue
            out.append(Observation(observation_date=date.fromisoformat(d), value=float(v), source_url=raw.source_url))
        return out
