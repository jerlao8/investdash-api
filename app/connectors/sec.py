"""SEC EDGAR connector.

Used by the AI Company Monitor to pull real company-facts XBRL data as a proof of concept
(Section 48's full extraction pipeline is out of scope for this build; this demonstrates the
deterministic-XBRL step only, for one or more tickers). series_identifier is
"{cik10}:{us_gaap_tag}", e.g. "0001045810:CashAndCashEquivalentsAtCarryingValue".

SEC requires a descriptive User-Agent header on every request (fair-access rule) - see
SEC_USER_AGENT in config.
"""

from __future__ import annotations

from datetime import date, timedelta

from app.connectors.base import BaseConnector, Observation, RawObservation, http_get_with_retry
from app.connectors.synthetic import MockParams, backfill_series
from app.timeutil import today_pt

SEC_COMPANYFACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik10}.json"


class SecConnector(BaseConnector):
    """Indicator-pipeline series (no ':' in series_identifier, e.g. composite AI-funding
    proxies like "N/A_HYPCAPEX") are synthetic-only - they're cross-company aggregates,
    not a single XBRL fetch. The real "{cik10}:{tag}" company-facts path is used
    separately by the AI Company Monitor seeding as a live-fetch proof of concept."""

    name = "SEC EDGAR"
    fixture_dir = "sec"

    def fetch(
        self,
        series_identifier: str,
        mock_params: MockParams | None = None,
        years: int = 12,
        frequency: str = "quarterly",
    ) -> RawObservation:
        if ":" not in series_identifier:
            return self._fetch_mock(
                series_identifier,
                mock_params or MockParams(base=10.0, vol=1.0),
                years,
                frequency=frequency,
            )
        cik10, tag = series_identifier.split(":", 1)
        if self.mode == "live":
            try:
                return self._fetch_live(cik10, tag)
            except Exception as exc:  # noqa: BLE001
                self._last_error = f"live fetch failed for {series_identifier}: {exc}"
        return RawObservation(series_identifier=series_identifier, payload={}, source_url="")

    def _fetch_mock(
        self, series_identifier: str, params: MockParams, years: int, frequency: str = "quarterly"
    ) -> RawObservation:
        end = today_pt()
        start = end - timedelta(days=365 * years)
        points = backfill_series(series_identifier, frequency, params, start, end)
        payload = {"observations": [{"date": d.isoformat(), "value": v} for d, v in points]}
        return RawObservation(series_identifier=series_identifier, payload=payload, source_url="https://www.sec.gov/")

    def _fetch_live(self, cik10: str, tag: str) -> RawObservation:
        url = SEC_COMPANYFACTS_URL.format(cik10=cik10)
        headers = {"User-Agent": self.settings.sec_user_agent}
        resp = http_get_with_retry(url, headers=headers)
        self._last_error = None
        return RawObservation(
            series_identifier=f"{cik10}:{tag}",
            payload=resp.json(),
            source_url=f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik10}",
        )

    def normalize(self, raw: RawObservation) -> list[Observation]:
        if not raw.payload:
            return []
        if "observations" in raw.payload:
            return [
                Observation(observation_date=date.fromisoformat(row["date"]), value=float(row["value"]), source_url=raw.source_url)
                for row in raw.payload["observations"]
            ]
        cik10, tag = raw.series_identifier.split(":", 1)
        try:
            units = raw.payload["facts"]["us-gaap"][tag]["units"]
        except KeyError:
            return []
        out: list[Observation] = []
        for unit_key, entries in units.items():
            for entry in entries:
                if entry.get("form") not in ("10-Q", "10-K"):
                    continue
                end = entry.get("end")
                val = entry.get("val")
                if end is None or val is None:
                    continue
                out.append(
                    Observation(observation_date=date.fromisoformat(end), value=float(val), source_url=raw.source_url)
                )
        return out
