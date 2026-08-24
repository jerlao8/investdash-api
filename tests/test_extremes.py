from app.scoring.extremes import LAST_RECESSION_START, extreme_flag


def test_last_recession_start_is_most_recent_seeded_recession():
    # Section 41's seeded event list includes the 2020 COVID crash as the most recent
    # NBER-dated recession - this should be derived, not hardcoded, so it stays correct as
    # future events get added to seed/events.py.
    assert LAST_RECESSION_START.year == 2020


def test_new_high_higher_is_healthy_is_positive():
    kind, tone = extreme_flag(current=100, hist_min=0, hist_max=100, polarity="higher_is_healthy")
    assert kind == "new_high"
    assert tone == "positive"


def test_new_high_lower_is_healthy_is_negative():
    kind, tone = extreme_flag(current=100, hist_min=0, hist_max=100, polarity="lower_is_healthy")
    assert kind == "new_high"
    assert tone == "negative"


def test_new_low_lower_is_healthy_is_positive():
    kind, tone = extreme_flag(current=0, hist_min=0, hist_max=100, polarity="lower_is_healthy")
    assert kind == "new_low"
    assert tone == "positive"


def test_custom_polarity_is_neutral_tone():
    kind, tone = extreme_flag(current=100, hist_min=0, hist_max=100, polarity="custom")
    assert kind is not None
    assert tone == "neutral"


def test_near_high_within_band():
    # range is 0-100, band = 5% = 5. 96 should be "near_high", not "new_high".
    kind, tone = extreme_flag(current=96, hist_min=0, hist_max=100, polarity="higher_is_healthy")
    assert kind == "near_high"


def test_middle_of_range_has_no_flag():
    kind, tone = extreme_flag(current=50, hist_min=0, hist_max=100, polarity="higher_is_healthy")
    assert kind is None and tone is None


def test_zero_range_returns_none():
    kind, tone = extreme_flag(current=5, hist_min=5, hist_max=5, polarity="higher_is_healthy")
    assert kind is None and tone is None
