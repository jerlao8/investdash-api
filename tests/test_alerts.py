from app.scoring.aggregate import ScoredIndicator
from app.scoring.alerts import detect_emergency, indicator_alert_level
from app.scoring.health_score import ScoreComponents, color_state


def _sc(slug, cluster, level, velocity=30.0, z=0.0, color=None):
    comps = ScoreComponents(level=level, velocity=velocity, persistence=50.0, z_score=z, percentile_full=level, direction="negative")
    s = ScoredIndicator(slug=slug, cluster=cluster, category="x", components=comps)
    s.health_score = level
    s.color = color or color_state(level)
    s.stress_percentile = 100 - level
    return s


def test_indicator_alert_level_red_on_high_stress_percentile():
    s = _sc("a", "credit", level=5)  # stress_percentile = 95
    assert indicator_alert_level(s) == "red"


def test_indicator_alert_level_warning_on_yellow_color():
    s = _sc("a", "credit", level=50, color="yellow")
    assert indicator_alert_level(s) == "warning"


def test_indicator_alert_level_info_when_healthy():
    s = _sc("a", "credit", level=90, color="green")
    assert indicator_alert_level(s) == "info"


def test_detect_emergency_requires_credit_and_equity_vol_clusters():
    # Four deteriorating clusters, but none in credit/liquidity/banking -> no emergency.
    scored = (
        [_sc(f"g{i}", "growth", level=20, velocity=20) for i in range(2)]
        + [_sc(f"l{i}", "labor", level=20, velocity=20) for i in range(2)]
        + [_sc(f"i{i}", "inflation", level=20, velocity=20) for i in range(2)]
        + [_sc(f"r{i}", "rates", level=20, velocity=20) for i in range(2)]
    )
    is_emergency, clusters = detect_emergency(scored)
    assert is_emergency is False


def test_detect_emergency_fires_with_credit_liquidity_and_equity_vol():
    scored = (
        [_sc(f"c{i}", "credit", level=15, velocity=20) for i in range(2)]
        + [_sc(f"l{i}", "liquidity", level=15, velocity=20) for i in range(2)]
        + [_sc(f"v{i}", "volatility_options", level=15, velocity=20) for i in range(2)]
        + [_sc(f"b{i}", "banking", level=15, velocity=20) for i in range(2)]
    )
    is_emergency, clusters = detect_emergency(scored)
    assert is_emergency is True
    assert "credit" in clusters and "volatility_options" in clusters


def test_detect_emergency_false_when_clusters_healthy():
    scored = [_sc(f"c{i}", "credit", level=90, velocity=80) for i in range(3)]
    is_emergency, _ = detect_emergency(scored)
    assert is_emergency is False


def test_detect_emergency_no_longer_fires_on_three_clusters_of_mild_yellow():
    # This is exactly the scenario the old >=3-clusters/50%-yellow-or-worse bar would have
    # fired on: three clusters, each just barely a majority yellow with below-median (but not
    # accelerating) velocity - ordinary cross-market noise, not a corroborated crisis signal.
    scored = (
        [_sc(f"c{i}", "credit", level=55, velocity=45, color="yellow") for i in range(2)]
        + [_sc(f"l{i}", "liquidity", level=55, velocity=45, color="yellow") for i in range(2)]
        + [_sc(f"v{i}", "volatility_options", level=55, velocity=45, color="yellow") for i in range(2)]
    )
    is_emergency, _ = detect_emergency(scored)
    assert is_emergency is False


def test_detect_emergency_requires_four_clusters_now():
    # Three clearly red, corroborating clusters used to be enough - now it isn't.
    scored = (
        [_sc(f"c{i}", "credit", level=15, velocity=20) for i in range(2)]
        + [_sc(f"l{i}", "liquidity", level=15, velocity=20) for i in range(2)]
        + [_sc(f"v{i}", "volatility_options", level=15, velocity=20) for i in range(2)]
    )
    is_emergency, _ = detect_emergency(scored)
    assert is_emergency is False
