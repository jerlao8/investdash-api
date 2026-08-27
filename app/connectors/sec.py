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

        # Cash-flow-statement concepts (capex, operating cash flow, ...) mix THREE duration
        # conventions under the same tag within a single filing: a genuinely discrete quarter
        # (~91 days), a year-to-date cumulative since the fiscal year start (~182/~273/~365
        # days, sharing that start with the other quarters of the same fiscal year), and -
        # confusingly - a trailing-twelve-month comparative (~365 days) whose start does NOT
        # align with the fiscal year and which shares its start with no other entry. Treating
        # every entry's "val" as its own discrete quarter mixes all three and produces
        # nonsense magnitudes/deltas (e.g. a lone TTM entry read as "this quarter").
        #
        # Fix: dedupe re-filed (start,end) pairs keeping the latest filing, then group by
        # "start". A genuine discrete quarter is a lone ~91-day entry - keep it as-is. A real
        # fiscal-year cumulative ladder has 2+ entries sharing a start (Q1, Q1+Q2, Q1+Q2+Q3,
        # FY) - diff consecutive ends to recover each discrete quarter. A lone entry that
        # ISN'T ~91 days (a standalone TTM or odd stub period, since it has no siblings to
        # diff against) is dropped rather than risk reporting a YTD/TTM total as one quarter.
        by_key: dict[tuple[str, str], dict] = {}
        for entries in units.values():
            for entry in entries:
                if entry.get("form") not in ("10-Q", "10-K"):
                    continue
                start, end, val = entry.get("start"), entry.get("end"), entry.get("val")
                if start is None or end is None or val is None:
                    continue
                key = (start, end)
                existing = by_key.get(key)
                if existing is None or entry.get("filed", "") >= existing.get("filed", ""):
                    by_key[key] = entry

        by_start: dict[str, list[dict]] = {}
        for entry in by_key.values():
            by_start.setdefault(entry["start"], []).append(entry)

        def _duration(entry: dict) -> int:
            return (date.fromisoformat(entry["end"]) - date.fromisoformat(entry["start"])).days

        out: list[Observation] = []
        for group in by_start.values():
            group.sort(key=lambda e: e["end"])
            # A trailing-twelve-month comparative fact spans exactly 4 quarters, so its start
            # always lands exactly on some real quarter's discrete-start date - it collides
            # with, and would otherwise corrupt, that quarter's group. A genuine fiscal-year
            # ladder is the only case with a true ~182-day (H1) or ~273-day (9-month) member;
            # a TTM collision never has one (just the real ~91-day quarter + the ~365-day TTM
            # fact), so requiring that signature before trusting the group as a ladder is what
            # tells the two apart.
            has_ladder_signature = any(170 <= _duration(e) <= 190 or 260 <= _duration(e) <= 285 for e in group)
            if len(group) == 1 or not has_ladder_signature:
                for entry in group:
                    if 80 <= _duration(entry) <= 100:
                        out.append(
                            Observation(
                                observation_date=date.fromisoformat(entry["end"]), value=float(entry["val"]),
                                source_url=raw.source_url,
                            )
                        )
                continue
            prior_val = None
            for entry in group:
                val = float(entry["val"])
                if prior_val is not None:
                    out.append(
                        Observation(
                            observation_date=date.fromisoformat(entry["end"]), value=val - prior_val,
                            source_url=raw.source_url,
                        )
                    )
                elif _duration(entry) <= 100:
                    # First rung of the ladder doubles as the discrete Q1 only when it's
                    # actually quarter-length; a longer first rung is a partial-year baseline
                    # with nothing to diff against, so it's used only to seed later diffs.
                    out.append(
                        Observation(
                            observation_date=date.fromisoformat(entry["end"]), value=val, source_url=raw.source_url
                        )
                    )
                prior_val = val
        out.sort(key=lambda o: o.observation_date)
        return out
