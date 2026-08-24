"""Hierarchical U.S. Equity Health Score (PRD Section 6) + cross-asset corroboration.

Two-pass design:
  1. compute_components() (health_score.py) scores each indicator from its own history.
  2. compute_corroboration() looks across cluster peers to fill in the cross-asset term,
     then finalize() combines everything into the 0-100 indicator health score.
  3. Indicators are grouped by cluster, then clusters are averaged (not indicators) within
     each first-level factor - this is the anti-double-counting mechanism from Section 6:
     a factor with 6 volatility indicators and 1 credit indicator still gives volatility and
     credit one vote each, not 6-to-1.
"""

from __future__ import annotations

import statistics
from collections import defaultdict
from dataclasses import dataclass, field

from app.scoring.health_score import ScoreComponents, color_state, finalize_health_score

# Section 6's six first-level factors and their weights.
FACTOR_WEIGHTS = {
    "credit_funding": 0.25,
    "equity_internals": 0.20,
    "us_macro": 0.20,
    "liquidity": 0.15,
    "valuation_positioning": 0.10,
    "global_spillover": 0.10,
}

# ai_funding / ai_demand deliberately excluded: Section 2's header shows "AI Infrastructure
# Funding Score" as a parallel score alongside the 6-factor Equity Health, not a component
# folded into it (Section 6's weights sum to 100% without an AI slot).
CATEGORY_TO_FACTOR = {
    "credit_risk_appetite": "credit_funding",
    "banking_credit_creation": "credit_funding",
    "equity_breadth_internals": "equity_internals",
    "volatility_options": "equity_internals",
    "macro_growth": "us_macro",
    "macro_labor": "us_macro",
    "macro_inflation": "us_macro",
    "macro_fiscal": "us_macro",
    "macro_rates": "us_macro",
    "liquidity_funding": "liquidity",
    "valuation": "valuation_positioning",
    "sentiment_positioning": "valuation_positioning",
    "global_liquidity": "global_spillover",
    "global_fx": "global_spillover",
    "global_growth": "global_spillover",
    "global_inflation_rates": "global_spillover",
    "global_equities": "global_spillover",
    "global_commodities": "global_spillover",
}

STATUS_THRESHOLDS = [(7.5, "Healthy"), (6.0, "Caution"), (4.0, "Warning")]


def status_from_score(score: float) -> str:
    for threshold, label in STATUS_THRESHOLDS:
        if score >= threshold:
            return label
    return "Emergency"


@dataclass
class ScoredIndicator:
    slug: str
    cluster: str
    category: str
    components: ScoreComponents
    green_threshold: float = 70.0
    yellow_threshold: float = 40.0
    confidence: float = 100.0
    is_stale: bool = False
    corroboration: float = 50.0
    health_score: float = 0.0
    color: str = "gray"
    stress_percentile: float = 0.0
    indicator_id: int | None = None
    observation_id: int | None = None


def compute_corroboration(scored: list[ScoredIndicator]) -> None:
    by_cluster: dict[str, list[ScoredIndicator]] = defaultdict(list)
    for s in scored:
        by_cluster[s.cluster].append(s)
    for s in scored:
        peers = [p for p in by_cluster[s.cluster] if p is not s]
        if not peers:
            s.corroboration = 50.0
            continue
        is_unhealthy = s.components.level < 50
        agree = sum(1 for p in peers if (p.components.level < 50) == is_unhealthy)
        s.corroboration = 100.0 * agree / len(peers)


def finalize_scores(scored: list[ScoredIndicator]) -> None:
    for s in scored:
        if s.is_stale:
            s.health_score = s.components.level  # keep a value, but color forces gray below
            s.color = "gray"
        else:
            s.health_score = finalize_health_score(
                s.components.level, s.components.velocity, s.components.persistence, s.corroboration
            )
            s.color = color_state(s.health_score, s.green_threshold, s.yellow_threshold)
        s.stress_percentile = round(100 - s.components.level, 1)


def _cluster_averaged_score(indicators: list[ScoredIndicator]) -> float:
    non_stale = [s for s in indicators if not s.is_stale]
    pool = non_stale or indicators
    if not pool:
        return 50.0
    by_cluster: dict[str, list[float]] = defaultdict(list)
    for s in pool:
        by_cluster[s.cluster].append(s.health_score)
    cluster_means = [statistics.mean(v) for v in by_cluster.values()]
    return statistics.mean(cluster_means)


@dataclass
class FactorScores:
    scores_0_10: dict[str, float] = field(default_factory=dict)
    ai_funding_0_10: float = 5.0
    overall_0_10: float = 5.0
    overall_status: str = "Caution"


def compute_factor_scores(scored: list[ScoredIndicator]) -> FactorScores:
    by_factor: dict[str, list[ScoredIndicator]] = defaultdict(list)
    ai_funding_indicators: list[ScoredIndicator] = []
    for s in scored:
        factor = CATEGORY_TO_FACTOR.get(s.category)
        if factor:
            by_factor[factor].append(s)
        if s.category == "ai_funding":
            ai_funding_indicators.append(s)

    scores_0_10 = {
        factor: round(_cluster_averaged_score(by_factor.get(factor, [])) / 10, 2) for factor in FACTOR_WEIGHTS
    }
    ai_funding_0_10 = round(_cluster_averaged_score(ai_funding_indicators) / 10, 2) if ai_funding_indicators else 5.0

    overall = sum(FACTOR_WEIGHTS[f] * scores_0_10.get(f, 5.0) for f in FACTOR_WEIGHTS)

    low3 = sum(1 for f in FACTOR_WEIGHTS if scores_0_10.get(f, 10) <= 3)
    low2 = sum(1 for f in FACTOR_WEIGHTS if scores_0_10.get(f, 10) <= 2)
    if low2 >= 4:
        overall -= 1.0
    elif low3 >= 3:
        overall -= 0.5

    overall = max(0.0, min(10.0, overall))
    status = status_from_score(overall)

    return FactorScores(scores_0_10=scores_0_10, ai_funding_0_10=ai_funding_0_10, overall_0_10=round(overall, 2), overall_status=status)
