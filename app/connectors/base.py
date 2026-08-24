"""Shared connector framework (PRD Section 36).

Every source connector implements fetch/normalize/source_health. Connectors default to
reading bundled fixture JSON (DATA_SOURCE_MODE=mock) shaped identically to the real API
response, and switch to a real HTTP call when DATA_SOURCE_MODE=live and credentials are
configured. This keeps the whole pipeline runnable with zero API keys while making the
swap to live data a config change rather than a rewrite.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Protocol

import httpx

from app.config import get_settings

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@dataclass
class RawObservation:
    series_identifier: str
    payload: Any  # raw, unparsed provider response for this series
    fetched_at: datetime = field(default_factory=datetime.utcnow)
    source_url: str = ""


@dataclass
class Observation:
    observation_date: date
    value: float
    source_url: str = ""
    is_preliminary: bool = False
    vintage_date: date | None = None


@dataclass
class SourceHealth:
    name: str
    ok: bool
    mode: str  # mock | live
    detail: str = ""
    checked_at: datetime = field(default_factory=datetime.utcnow)


class DataConnector(Protocol):
    def fetch(self, series_identifier: str) -> RawObservation: ...

    def normalize(self, raw: RawObservation) -> list[Observation]:
        ...

    def source_health(self) -> SourceHealth: ...


def is_proxy_series(series_identifier: str) -> bool:
    """Indicators without one real single-series source (composite proxies like breadth %,
    CAPE, or dashboard-native indices) use an "N/A_..." series_identifier in the seed data.
    Connectors should skip the live-fetch attempt entirely for these rather than wasting
    retries/backoff hitting a real API with a series ID that was never going to exist."""
    return series_identifier.startswith("N/A_")


def raw_payload_hash(payload: Any) -> str:
    blob = json.dumps(payload, sort_keys=True, default=str).encode()
    return hashlib.sha256(blob).hexdigest()


def load_fixture(connector: str, series_identifier: str) -> Any:
    path = FIXTURES_DIR / connector / f"{series_identifier}.json"
    if not path.exists():
        raise FileNotFoundError(f"No fixture for {connector}/{series_identifier}")
    return json.loads(path.read_text())


def http_get_with_retry(
    url: str, params: dict | None = None, headers: dict | None = None, max_retries: int = 3
) -> httpx.Response:
    """Simple retry-with-exponential-backoff wrapper used by live connectors."""
    last_exc: Exception | None = None
    for attempt in range(max_retries):
        try:
            resp = httpx.get(url, params=params, headers=headers, timeout=15.0)
            resp.raise_for_status()
            return resp
        except Exception as exc:  # noqa: BLE001 - deliberately broad, we retry then re-raise
            last_exc = exc
            time.sleep(min(2**attempt, 8))
    assert last_exc is not None
    raise last_exc


class BaseConnector:
    """Common mock/live switch + source_health bookkeeping shared by all connectors."""

    name: str = "base"
    fixture_dir: str = "base"

    def __init__(self) -> None:
        self.settings = get_settings()
        self._last_error: str | None = None

    @property
    def mode(self) -> str:
        return self.settings.data_source_mode

    def source_health(self) -> SourceHealth:
        return SourceHealth(
            name=self.name,
            ok=self._last_error is None,
            mode=self.mode,
            detail=self._last_error or "ok",
        )
