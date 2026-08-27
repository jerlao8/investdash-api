from app.seed.indicators import INDICATORS


def test_lei_is_deactivated():
    """USSLIND (the series backing "lei") was discontinued by FRED itself in April 2020 -
    no pipeline fix can produce newer data for it, so it must stay inactive rather than
    perpetually showing years-stale data on the dashboard."""
    lei = next(i for i in INDICATORS if i["slug"] == "lei")
    assert lei["active"] is False


def test_indicators_are_active_by_default():
    active_count = sum(1 for i in INDICATORS if i["active"])
    # Every indicator except the one known-discontinued series should be active.
    assert active_count == len(INDICATORS) - 1
