"""Mock-only stub connectors: BIS, BLS, BEA, SIA/WSTS, FINRA, CFTC.

These implement the same DataConnector interface as the live connectors but only ever
generate synthetic data - they are extension points, not real integrations. Wiring up a
real HTTP call for one of these later means adding a `_fetch_live` method the same way
fred.py/treasury.py/etc. already do, without touching the pipeline or scoring layers.
"""

from __future__ import annotations

from datetime import date, timedelta

from app.connectors.base import BaseConnector, Observation, RawObservation
from app.connectors.synthetic import MockParams, backfill_series


class MockOnlyConnector(BaseConnector):
    base_url: str = ""

    def fetch(self, series_identifier: str, mock_params: MockParams | None = None, years: int = 12) -> RawObservation:
        end = date.today()
        start = end - timedelta(days=365 * years)
        params = mock_params or MockParams(base=1.0, vol=0.05)
        points = backfill_series(series_identifier, "monthly", params, start, end)
        payload = {"observations": [{"date": d.isoformat(), "value": v} for d, v in points]}
        self._last_error = "mock-only connector: no live integration implemented yet"
        return RawObservation(series_identifier=series_identifier, payload=payload, source_url=self.base_url)

    def normalize(self, raw: RawObservation) -> list[Observation]:
        return [
            Observation(observation_date=date.fromisoformat(row["date"]), value=float(row["value"]), source_url=raw.source_url)
            for row in raw.payload.get("observations", [])
        ]

    def source_health(self):
        h = super().source_health()
        h.ok = False  # always flagged not-live so the data-health page is honest about it
        return h


class BisConnector(MockOnlyConnector):
    name = "BIS"
    base_url = "https://www.bis.org/statistics/"


class BlsConnector(MockOnlyConnector):
    name = "BLS"
    base_url = "https://www.bls.gov/data/"


class BeaConnector(MockOnlyConnector):
    name = "BEA"
    base_url = "https://www.bea.gov/data"


class SiaWstsConnector(MockOnlyConnector):
    name = "SIA/WSTS"
    base_url = "https://www.semiconductors.org/data-resources/"


class FinraConnector(MockOnlyConnector):
    name = "FINRA"
    base_url = "https://www.finra.org/investors/markets"


class CftcConnector(MockOnlyConnector):
    name = "CFTC"
    base_url = "https://www.cftc.gov/MarketReports/CommitmentsofTraders/"
