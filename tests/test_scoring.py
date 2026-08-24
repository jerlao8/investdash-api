from app.scoring.aggregate import (
    CATEGORY_TO_FACTOR,
    FACTOR_WEIGHTS,
    ScoredIndicator,
    compute_corroboration,
    compute_factor_scores,
    finalize_scores,
)
from app.scoring.fear_greed import compute_fear_greed_index, fear_greed_label
from app.scoring.health_score import ScoreComponents, color_state, compute_components, finalize_health_score, reading_guide
from app.scoring.normalize import percentile_rank, robust_z_score


def test_percentile_rank_at_extremes():
    history = list(range(1, 101))  # 1..100
    assert percentile_rank(100, history) == 100.0
    assert percentile_rank(0, history) == 0.0
    assert 49.0 <= percentile_rank(50, history) <= 51.0


def test_percentile_rank_neutral_on_thin_history():
    assert percentile_rank(5.0, []) == 50.0
    assert percentile_rank(5.0, [5.0]) == 50.0


def test_robust_z_score_zero_at_median():
    history = [1, 2, 3, 4, 5, 6, 7, 8, 9]
    assert robust_z_score(5, history) == 0.0


def test_compute_components_higher_is_healthy_high_value_scores_well():
    history = [float(x) for x in range(1, 200)]
    comps = compute_components("test-higher", 195.0, history[-60:], history, history, "higher_is_healthy")
    assert comps.level > 90


def test_compute_components_lower_is_healthy_high_value_scores_poorly():
    history = [float(x) for x in range(1, 200)]
    comps = compute_components("test-lower", 195.0, history[-60:], history, history, "lower_is_healthy")
    assert comps.level < 10


def test_raw_trend_reflects_literal_movement_regardless_of_polarity():
    # A rising raw value: raw_trend is "up" whether that rise is healthy or not.
    history = [float(x) for x in range(1, 200)]
    comps_higher = compute_components("test-a", 199.0, history[-60:], history, history, "higher_is_healthy")
    comps_lower = compute_components("test-b", 199.0, history[-60:], history, history, "lower_is_healthy")
    assert comps_higher.raw_trend == "up"
    assert comps_lower.raw_trend == "up"  # same literal movement even though it's unhealthy here
    # direction (health-oriented) diverges even though raw_trend agrees:
    assert comps_higher.direction == "positive"
    assert comps_lower.direction == "negative"


def test_color_state_thresholds():
    assert color_state(80, 70, 40) == "green"
    assert color_state(70, 70, 40) == "green"
    assert color_state(69.9, 70, 40) == "yellow"
    assert color_state(40, 70, 40) == "yellow"
    assert color_state(39.9, 70, 40) == "red"


def test_finalize_health_score_weights_sum_to_full_range():
    score = finalize_health_score(100, 100, 100, 100)
    assert score == 100.0
    score = finalize_health_score(0, 0, 0, 0)
    assert score == 0.0


def _sc(slug, cluster, category, level, velocity=50.0, persistence=50.0):
    return ScoredIndicator(
        slug=slug, cluster=cluster, category=category,
        components=ScoreComponents(level=level, velocity=velocity, persistence=persistence, z_score=0.0, percentile_full=level, direction="flat"),
    )


def test_corroboration_agrees_with_unhealthy_peers():
    peers = [_sc("a", "credit", "credit_risk_appetite", 20), _sc("b", "credit", "credit_risk_appetite", 25), _sc("c", "credit", "credit_risk_appetite", 15)]
    compute_corroboration(peers)
    for p in peers:
        assert p.corroboration == 100.0  # all three unhealthy -> full agreement among peers


def test_factor_scores_cluster_averaging_prevents_indicator_count_dominance():
    # 6 volatility indicators all healthy (level=90) vs 1 credit indicator unhealthy (level=10).
    # Cluster-averaged factor score should NOT be dragged to ~88 by sheer indicator count.
    scored = [_sc(f"vol{i}", "volatility_options", "volatility_options", 90) for i in range(6)]
    scored.append(_sc("credit1", "credit", "credit_risk_appetite", 10))
    compute_corroboration(scored)
    finalize_scores(scored)
    factors = compute_factor_scores(scored)
    equity_internals = factors.scores_0_10["equity_internals"]
    credit_funding = factors.scores_0_10["credit_funding"]
    assert equity_internals > 7  # volatility cluster still healthy
    assert credit_funding <= 3.0  # credit cluster is its own vote, not diluted by 6-vs-1 indicator count


def test_overall_weights_sum_to_one():
    assert abs(sum(FACTOR_WEIGHTS.values()) - 1.0) < 1e-9


def test_reading_guide_explains_arrow_is_health_oriented_for_lower_is_healthy():
    guide = reading_guide("lower_is_healthy")
    assert "arrow" in guide.lower()
    assert "value likely fell" in guide  # clarifies UP arrow can correspond to a FALLING raw value


def test_reading_guide_higher_is_healthy_tracks_raw_value_directly():
    guide = reading_guide("higher_is_healthy")
    assert "rose (favorable)" in guide


def test_reading_guide_custom_flags_non_monotonic():
    guide = reading_guide("custom")
    assert "doesn't move monotonically" in guide


def test_category_to_factor_covers_known_categories():
    assert CATEGORY_TO_FACTOR["credit_risk_appetite"] == "credit_funding"
    assert CATEGORY_TO_FACTOR["macro_rates"] == "us_macro"
    assert "ai_funding" not in CATEGORY_TO_FACTOR  # parallel score, not part of the weighted overall


def _fg(slug, health_score, is_stale=False):
    s = _sc(slug, "x", "x", health_score)
    s.health_score = health_score
    s.is_stale = is_stale
    return s


def test_fear_greed_none_with_too_few_components():
    scored = {"vix": _fg("vix", 80), "hy-oas": _fg("hy-oas", 80)}
    assert compute_fear_greed_index(scored) is None


def test_fear_greed_high_when_calm_components_healthy():
    scored = {
        "vix": _fg("vix", 90),
        "equity-put-call": _fg("equity-put-call", 90),
        "pct-above-200dma": _fg("pct-above-200dma", 90),
        "hy-oas": _fg("hy-oas", 90),
        "spx-level": _fg("spx-level", 90),
    }
    value = compute_fear_greed_index(scored)
    assert value is not None and value > 80
    assert fear_greed_label(value) == "Extreme Greed"


def test_fear_greed_margin_debt_is_inverted():
    # Margin debt scored "unhealthy" (low health_score = high leverage) should INCREASE greed.
    healthy_components = {
        "vix": _fg("vix", 50),
        "equity-put-call": _fg("equity-put-call", 50),
        "pct-above-200dma": _fg("pct-above-200dma", 50),
        "hy-oas": _fg("hy-oas", 50),
    }
    with_low_margin_health = dict(healthy_components, **{"margin-debt-mktcap": _fg("margin-debt-mktcap", 10)})
    value = compute_fear_greed_index(with_low_margin_health)
    assert value is not None and value > 50  # low health (high leverage) pushes greed UP, not down


def test_fear_greed_ignores_stale_components():
    scored = {
        "vix": _fg("vix", 90),
        "equity-put-call": _fg("equity-put-call", 90),
        "pct-above-200dma": _fg("pct-above-200dma", 90, is_stale=True),
        "hy-oas": _fg("hy-oas", 90),
        "spx-level": _fg("spx-level", 90),
    }
    value = compute_fear_greed_index(scored)
    assert value == 90.0  # the stale one is excluded, not averaged in
