from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel


class HealthOverview(BaseModel):
    snapshot_date: date | None
    us_equity_score: float
    us_macro_score: float
    global_score: float
    liquidity_score: float
    credit_score: float
    ai_funding_score: float
    valuation_score: float
    equity_internals_score: float
    fear_greed_index: float | None = None
    fear_greed_change_1d: float | None = None
    overall_status: str
    score_change_1d: float | None = None
    score_change_1m: float | None = None
    global_score_change_1d: float | None = None
    liquidity_score_change_1d: float | None = None
    credit_score_change_1d: float | None = None
    us_macro_score_change_1d: float | None = None
    ai_funding_score_change_1d: float | None = None
    sparkline_90d: list[float] = []
    last_refresh: datetime | None = None
    stale_indicator_count: int = 0
    emergency_count: int = 0
    warning_count: int = 0
    green_count: int = 0
    yellow_count: int = 0
    red_count: int = 0


class IndicatorCard(BaseModel):
    slug: str
    name: str
    category: str
    subcategory: str | None
    cluster: str
    frequency: str
    units: str
    lead_lag: str
    crisis_relevance: str
    is_critical: bool
    is_favorited: bool = False
    current_value: float | None
    color_state: str
    direction: str  # positive|negative|flat - health-oriented, drives arrow COLOR
    raw_trend: str = "flat"  # up|down|flat - literal value movement, drives arrow SHAPE
    stress_percentile: float | None
    health_score: float | None
    change_1d: float | None
    change_5d: float | None
    change_1m: float | None
    last_observation_date: date | None
    source_updated_today: bool = False
    confidence: float | None
    is_stale: bool
    info_text: str
    health_polarity: str
    reading_guide: str
    extreme_kind: str | None = None
    extreme_since: date | None = None
    extreme_tone: str | None = None
    source_name: str
    source_url: str


class IndicatorHistoryPoint(BaseModel):
    date: date
    value: float
    health_score: float | None = None
    color_state: str | None = None


class IndicatorDetail(BaseModel):
    card: IndicatorCard
    history: list[IndicatorHistoryPoint]


class FeedItemOut(BaseModel):
    id: int
    date: date
    posted_at: datetime
    priority: int
    category: str
    headline: str
    summary: str
    source_url: str
    severity: str | None = None
    direction: str | None = None
    equity_implication: str | None = None


class CompanyOut(BaseModel):
    id: int
    name: str
    ticker: str
    sector: str
    subsector: str
    tier: str
    overall_score: float | None = None
    liquidity_score: float | None = None
    debt_score: float | None = None
    fcf_score: float | None = None
    capex_score: float | None = None
    maturity_score: float | None = None
    funding_gap: float | None = None
    funding_gap_score: float | None = None


class CompanyDetail(CompanyOut):
    metrics: dict[str, float]


class DataHealthSource(BaseModel):
    name: str
    mode: str
    ok: bool
    detail: str


class DataHealthOut(BaseModel):
    sources: list[DataHealthSource]
    stale_indicators: list[str]
    total_indicators: int
    last_pipeline_run: datetime | None = None


class CrisisEventOut(BaseModel):
    id: int
    name: str
    event_start: date
    event_end: date | None
    peak_to_trough_drawdown: float | None
    recession_start: date | None
    recession_end: date | None
    description: str
    # Applied U.S. Equity Health (current algorithm) reconstructed from observations as of
    # event_start — i.e. crash/peak failure date — not a stored MarketSnapshot.
    us_equity_score_at_start: float | None = None
    overall_status_at_start: str | None = None


class BacktestReconstruction(BaseModel):
    event: CrisisEventOut
    pre_event_scores: list[dict]


class PeriodComparisonOut(BaseModel):
    label: str
    lookback_date: date | None
    deltas: dict[str, float | None]
    pct_deltas: dict[str, float | None]


class SummaryBlockOut(BaseModel):
    title: str
    tone: str
    sentences: list[str]


class DailySummaryOut(BaseModel):
    generated_at: datetime
    snapshot_date: date
    overall_score: float
    overall_status: str
    headline: str
    comparisons: list[PeriodComparisonOut]
    blocks: list[SummaryBlockOut]
