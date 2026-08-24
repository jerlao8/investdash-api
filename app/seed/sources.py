"""`sources` table seed (PRD Section 35/37) - one row per connector."""

from __future__ import annotations

from typing import Any

SOURCES: list[dict[str, Any]] = [
    dict(key="fred", name="FRED / ALFRED", base_url="https://fred.stlouisfed.org/", provider_type="official",
         requires_api_key=True, rate_limit="120 req/min", license_notes="Free, public domain federal data.",
         commercial_display_allowed=True, priority=1),
    dict(key="treasury", name="U.S. Treasury", base_url="https://home.treasury.gov/", provider_type="official",
         requires_api_key=False, rate_limit="unspecified", license_notes="Free, public domain federal data.",
         commercial_display_allowed=True, priority=1),
    dict(key="nyfed", name="New York Fed", base_url="https://markets.newyorkfed.org/", provider_type="official",
         requires_api_key=False, rate_limit="unspecified", license_notes="Free, public domain federal data.",
         commercial_display_allowed=True, priority=1),
    dict(key="cboe", name="Cboe", base_url="https://www.cboe.com/", provider_type="official",
         requires_api_key=False, rate_limit="unspecified", license_notes="Free public historical index data; detailed DataShop datasets are paid and excluded.",
         commercial_display_allowed=False, priority=1),
    dict(key="sec", name="SEC EDGAR", base_url="https://www.sec.gov/", provider_type="official",
         requires_api_key=False, rate_limit="10 req/sec fair-access", license_notes="Free, public domain; requires descriptive User-Agent.",
         commercial_display_allowed=True, priority=1),
    dict(key="bis", name="BIS", base_url="https://www.bis.org/statistics/", provider_type="official",
         requires_api_key=False, rate_limit="unspecified", license_notes="Free public statistics.",
         commercial_display_allowed=True, priority=2),
    dict(key="bls", name="BLS", base_url="https://www.bls.gov/data/", provider_type="official",
         requires_api_key=False, rate_limit="500 req/day unregistered", license_notes="Free, public domain federal data.",
         commercial_display_allowed=True, priority=2),
    dict(key="bea", name="BEA", base_url="https://www.bea.gov/data", provider_type="official",
         requires_api_key=True, rate_limit="1000 req/min", license_notes="Free, public domain federal data.",
         commercial_display_allowed=True, priority=2),
    dict(key="sia_wsts", name="SIA / WSTS", base_url="https://www.semiconductors.org/data-resources/", provider_type="free_public",
         requires_api_key=False, rate_limit="unspecified", license_notes="Free monthly releases; detailed WSTS subscription data is paid and excluded.",
         commercial_display_allowed=False, priority=2),
    dict(key="finra", name="FINRA", base_url="https://www.finra.org/investors/markets", provider_type="official",
         requires_api_key=False, rate_limit="unspecified", license_notes="Free public statistics.",
         commercial_display_allowed=True, priority=2),
    dict(key="cftc", name="CFTC", base_url="https://www.cftc.gov/MarketReports/CommitmentsofTraders/", provider_type="official",
         requires_api_key=False, rate_limit="unspecified", license_notes="Free public statistics.",
         commercial_display_allowed=True, priority=2),
]
