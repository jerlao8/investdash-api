from datetime import date, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.models import MarketSnapshot
from app.db.session import Base
from app.scoring.daily_summary import _pick_longer_window, _tone, _trend_phrase, generate_daily_summary


def test_trend_phrase_signs_and_flat_band():
    assert _trend_phrase(None) == "not enough history yet"
    assert _trend_phrase(0.5) == "little changed"
    assert _trend_phrase(5.0) == "up 5.0%"
    assert _trend_phrase(-5.0) == "down 5.0%"


def test_tone_positive_healthy_and_stable():
    assert _tone(8.0, week_delta_pct=1.0) == "positive"


def test_tone_negative_low_score_or_sharp_drop():
    assert _tone(3.0, week_delta_pct=0.0) == "negative"
    assert _tone(6.0, week_delta_pct=-8.0) == "negative"


def test_tone_neutral_otherwise():
    assert _tone(6.0, week_delta_pct=0.0) == "neutral"


def test_tone_scale_aware_for_fear_greed_0_100():
    # 53/100 is "Neutral" on the fear/greed scale - must not read as "positive" just because
    # 53 > 7 (the 0-10 health-score threshold applied without scaling).
    assert _tone(53.0, week_delta_pct=1.0, scale=100.0) == "neutral"
    assert _tone(85.0, week_delta_pct=1.0, scale=100.0) == "positive"
    assert _tone(15.0, week_delta_pct=-10.0, scale=100.0) == "negative"


def _snapshot(db, snapshot_date, score):
    row = MarketSnapshot(
        snapshot_date=snapshot_date, us_equity_score=score, us_macro_score=score, global_score=score,
        liquidity_score=score, credit_score=score, ai_funding_score=score, valuation_score=score,
        equity_internals_score=score, fear_greed_index=score * 10, overall_status="Caution",
    )
    db.add(row)
    return row


def _make_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine, tables=[MarketSnapshot.__table__])
    return sessionmaker(bind=engine)()


def test_pick_longer_window_prefers_quarter_then_year_then_month():
    db = _make_session()
    today = date(2026, 8, 23)
    current = _snapshot(db, today, 6.0)
    _snapshot(db, today - timedelta(days=91), 5.0)  # quarter ago: (6-5)/5 = +20%
    db.commit()

    from app.scoring.daily_summary import compute_period_comparisons

    comparisons = compute_period_comparisons(db, current)
    label, pct_delta = _pick_longer_window(comparisons, "us_equity_score")
    assert label == "quarter"
    assert pct_delta == 20.0


def test_generate_daily_summary_produces_headline_and_percentage_trends():
    db = _make_session()
    today = date(2026, 8, 23)
    current = _snapshot(db, today, 7.5)
    _snapshot(db, today - timedelta(days=7), 6.5)  # (7.5-6.5)/6.5 = +15.4%
    db.commit()

    headline, comparisons, blocks = generate_daily_summary(db, current, red_count=5, yellow_count=10, green_count=90, emergency_count=0)

    assert "U.S. Equity Health is 7.5/10" in headline
    assert "%" in headline  # percentage-based trend language, not absolute points
    assert len(comparisons) == 4
    assert comparisons[0].pct_deltas["us_equity_score"] is not None

    titles = [b.title for b in blocks]
    assert "Overall Market Health" in titles
    assert "Breadth & Alerts" in titles
    assert all(1 <= len(b.sentences) <= 3 for b in blocks)

    overall = next(b for b in blocks if b.title == "Overall Market Health")
    assert any("blends credit, liquidity" in s for s in overall.sentences)  # equity-relevance context sentence present


def test_generate_daily_summary_in_chinese_produces_chinese_text():
    db = _make_session()
    today = date(2026, 8, 23)
    current = _snapshot(db, today, 7.5)
    _snapshot(db, today - timedelta(days=7), 6.5)
    db.commit()

    headline, _, blocks = generate_daily_summary(
        db, current, red_count=5, yellow_count=10, green_count=90, emergency_count=0, lang="zh"
    )

    assert "美股健康度" in headline
    assert "%" in headline
    titles = [b.title for b in blocks]
    assert "整体市场健康度" in titles
    assert "市场广度与警报" in titles
