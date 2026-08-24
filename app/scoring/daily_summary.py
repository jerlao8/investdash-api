"""Deterministic daily market-health summary: current state + week/month/quarter/year
comparisons, rendered as short (1-3 sentence) blocks - never LLM-generated, same
"grounded in structured data" rule as the Daily Feed (Section 30).

Bilingual (en/zh): every sentence is generated fresh per request from structured numbers, so
supporting a second language is just a second set of phrase templates threaded through via a
`lang` param - no extra storage needed (this endpoint is computed live, not pipeline-baked).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.db.models import MarketSnapshot
from app.scoring.aggregate import status_from_score

PERIODS = [("1 Week Ago", 7), ("1 Month Ago", 30), ("1 Quarter Ago", 91), ("1 Year Ago", 365)]

FIELDS = [
    "us_equity_score", "liquidity_score", "credit_score", "us_macro_score",
    "global_score", "ai_funding_score", "equity_internals_score", "valuation_score", "fear_greed_index",
]

# Stable, language-agnostic block keys - used to look up both the display title and the
# equity-transmission-mechanism sentence in whichever language was requested, rather than
# using the (previously English-only) title text itself as the dict key.
BLOCK_TITLES = {
    "overall": ("Overall Market Health", "整体市场健康度"),
    "credit_liquidity": ("Credit & Liquidity", "信贷与流动性"),
    "equity_internals": ("Equity Internals & Breadth", "股票内部结构与广度"),
    "macro": ("U.S. Macro / Recession Risk", "美国宏观经济/衰退风险"),
    "global": ("Global Conditions", "全球状况"),
    "ai_funding": ("AI Infrastructure Funding", "AI基础设施融资"),
    "sentiment": ("Sentiment (Fear & Greed)", "市场情绪（恐惧与贪婪）"),
    "breadth": ("Breadth & Alerts", "市场广度与警报"),
}

# One deterministic sentence per block explaining the equity-market transmission mechanism -
# same spirit as alerts.py's CATEGORY_IMPLICATION, but for the factor-level summary blocks.
EQUITY_CONTEXT_EN = {
    "overall": (
        "This blends credit, liquidity, macro, breadth, valuation, and global signals into one read on U.S. equity "
        "risk - sustained multi-factor deterioration here has historically preceded corrections or bear markets."
    ),
    "credit_liquidity": (
        "Credit and liquidity conditions govern how easily companies can fund operations, capex, and buybacks - "
        "persistent tightening raises the odds of multiple compression and forced deleveraging in equities."
    ),
    "equity_internals": (
        "Breadth measures how many stocks are actually participating in market moves - narrowing breadth while the "
        "index holds up is a classic sign that gains are concentrated and fragile."
    ),
    "macro": (
        "Growth and labor deterioration feed directly into earnings estimates - this factor is the dashboard's "
        "best read on recession risk, historically the single biggest driver of bear markets."
    ),
    "global": (
        "U.S. equities are not immune to global stress - weakening international liquidity, growth, or FX "
        "conditions can spill into U.S. risk appetite and multinational earnings."
    ),
    "ai_funding": (
        "AI capex has driven a large share of recent index gains concentrated in a few mega-caps - funding stress "
        "here raises the risk of a capex pullback hitting both AI suppliers and the broader index."
    ),
    "sentiment": (
        "Extreme sentiment readings in either direction have historically preceded reversals - extreme greed can "
        "precede pullbacks, while extreme fear can mark local bottoms."
    ),
    "breadth": (
        "Corroborated stress across many indicators at once is a higher-confidence signal than any single data "
        "point - it's what separates routine noise from a move worth taking seriously."
    ),
}

EQUITY_CONTEXT_ZH = {
    "overall": (
        "该指标综合了信贷、流动性、宏观、广度、估值和全球信号，形成对美股风险的整体判断——"
        "多个因素持续同步恶化历来往往预示着回调或熊市的到来。"
    ),
    "credit_liquidity": (
        "信贷与流动性状况决定了企业为运营、资本开支和回购融资的难易程度——"
        "持续收紧会提高估值倍数压缩和被迫去杠杆的概率。"
    ),
    "equity_internals": (
        "广度衡量的是实际参与市场上涨的个股数量——"
        "指数维持强势而广度收窄，是涨幅集中且脆弱的典型信号。"
    ),
    "macro": (
        "增长与就业的恶化会直接影响盈利预期——"
        "该因子是仪表盘对衰退风险最重要的判断依据，历来是熊市最主要的驱动因素。"
    ),
    "global": (
        "美股并非对全球压力免疫——"
        "国际流动性、增长或汇率状况的走弱都可能波及美国的风险偏好和跨国公司盈利。"
    ),
    "ai_funding": (
        "AI资本开支带动了近期指数涨幅中相当大的一部分，且集中在少数几家超大市值公司——"
        "此处的融资压力增加了资本开支收缩同时冲击AI供应商和大盘的风险。"
    ),
    "sentiment": (
        "无论方向如何，极端的情绪读数历来往往预示着反转——"
        "极度贪婪可能预示回调，而极度恐惧则可能标志着阶段性底部。"
    ),
    "breadth": (
        "众多指标同时出现相互印证的压力信号，其可信度远高于任何单一数据点——"
        "这正是区分常规噪音与真正值得重视的走势的关键。"
    ),
}


@dataclass
class PeriodComparison:
    label: str
    lookback_date: date | None
    deltas: dict[str, float | None] = field(default_factory=dict)
    pct_deltas: dict[str, float | None] = field(default_factory=dict)


@dataclass
class SummaryBlock:
    title: str
    tone: str  # positive | neutral | negative
    sentences: list[str]


def _closest_snapshot(snapshots: list[MarketSnapshot], target: date, tolerance_days: int = 10) -> MarketSnapshot | None:
    candidates = [s for s in snapshots if abs((s.snapshot_date - target).days) <= tolerance_days]
    if not candidates:
        return None
    return min(candidates, key=lambda s: abs((s.snapshot_date - target).days))


def compute_period_comparisons(db: Session, current: MarketSnapshot) -> list[PeriodComparison]:
    cutoff = current.snapshot_date - timedelta(days=400)
    snapshots = db.query(MarketSnapshot).filter(MarketSnapshot.snapshot_date >= cutoff).all()

    out: list[PeriodComparison] = []
    for label, days_back in PERIODS:
        target = current.snapshot_date - timedelta(days=days_back)
        historical = _closest_snapshot(snapshots, target)
        deltas: dict[str, float | None] = {}
        pct_deltas: dict[str, float | None] = {}
        for f in FIELDS:
            cur_val = getattr(current, f)
            hist_val = getattr(historical, f) if historical else None
            if cur_val is not None and hist_val is not None:
                deltas[f] = round(cur_val - hist_val, 2)
                # Guard against a near-zero base blowing up the percentage into something meaningless.
                pct_deltas[f] = round((cur_val - hist_val) / hist_val * 100, 1) if abs(hist_val) >= 0.1 else None
            else:
                deltas[f] = None
                pct_deltas[f] = None
        out.append(
            PeriodComparison(
                label=label, lookback_date=historical.snapshot_date if historical else None,
                deltas=deltas, pct_deltas=pct_deltas,
            )
        )
    return out


def _trend_phrase(pct: float | None, lang: str = "en", flat_threshold: float = 2.0) -> str:
    if lang == "zh":
        if pct is None:
            return "历史数据不足"
        if pct > flat_threshold:
            return f"上涨{pct:.1f}%"
        if pct < -flat_threshold:
            return f"下跌{abs(pct):.1f}%"
        return "变化不大"

    if pct is None:
        return "not enough history yet"
    if pct > flat_threshold:
        return f"up {pct:.1f}%"
    if pct < -flat_threshold:
        return f"down {abs(pct):.1f}%"
    return "little changed"


_WINDOW_WORD = {
    "en": {"quarter": "quarter", "year": "year", "month": "month"},
    "zh": {"quarter": "季度", "year": "年", "month": "月"},
}


def _pick_longer_window(comparisons: list[PeriodComparison], field_name: str) -> tuple[str, float | None]:
    """Prefer quarter-ago; fall back to year-ago; fall back to month-ago - whichever has data.
    Returns an internal English key (quarter|year|month); callers translate via _WINDOW_WORD."""
    by_label = {c.label: c for c in comparisons}
    for label, key in (("1 Quarter Ago", "quarter"), ("1 Year Ago", "year"), ("1 Month Ago", "month")):
        c = by_label.get(label)
        if c and c.pct_deltas.get(field_name) is not None:
            return key, c.pct_deltas[field_name]
    return "quarter", None


def _tone(score: float, week_delta_pct: float | None, scale: float = 10.0) -> str:
    """scale=10 for health-style scores, scale=100 for the fear/greed index - the level
    thresholds scale with the score's own range; the trend thresholds are percentages, which
    are already scale-normalized."""
    high = 0.7 * scale
    low = 0.4 * scale
    if score >= high and (week_delta_pct is None or week_delta_pct >= -3.0):
        return "positive"
    if score < low or (week_delta_pct is not None and week_delta_pct <= -6.0):
        return "negative"
    return "neutral"


def _factor_block(block_key: str, score: float, unit: str, comparisons: list[PeriodComparison], field_name: str, lang: str = "en") -> SummaryBlock:
    by_label = {c.label: c for c in comparisons}
    week_delta_pct = by_label["1 Week Ago"].pct_deltas.get(field_name)
    longer_key, longer_delta_pct = _pick_longer_window(comparisons, field_name)
    longer_word = _WINDOW_WORD[lang][longer_key]

    title_en, title_zh = BLOCK_TITLES[block_key]
    title = title_zh if lang == "zh" else title_en

    scale = 100.0 if unit == "/100" else 10.0
    status = status_from_score(score) if unit == "/10" else None

    if lang == "zh":
        status_zh = {"Healthy": "健康", "Caution": "谨慎", "Warning": "警示", "Emergency": "紧急"}.get(status, status) if status else None
        level_sentence = f"{title}目前为{score:.1f}{unit}" + (f"（{status_zh}）。" if status_zh else "。")
        trend_sentence = f"较一周前{_trend_phrase(week_delta_pct, lang)}，较一{longer_word}前{_trend_phrase(longer_delta_pct, lang)}。"
    else:
        level_sentence = f"{title} is at {score:.1f}{unit}" + (f" ({status})." if status else ".")
        trend_sentence = f"That's {_trend_phrase(week_delta_pct, lang)} vs. a week ago and {_trend_phrase(longer_delta_pct, lang)} vs. a {longer_word} ago."

    context_sentence = (EQUITY_CONTEXT_ZH if lang == "zh" else EQUITY_CONTEXT_EN).get(block_key, "")

    sentences = [level_sentence, trend_sentence]
    if context_sentence:
        sentences.append(context_sentence)

    return SummaryBlock(title=title, tone=_tone(score, week_delta_pct, scale=scale), sentences=sentences)


def generate_daily_summary(
    db: Session,
    current: MarketSnapshot,
    red_count: int,
    yellow_count: int,
    green_count: int,
    emergency_count: int,
    lang: str = "en",
) -> tuple[str, list[PeriodComparison], list[SummaryBlock]]:
    comparisons = compute_period_comparisons(db, current)
    by_label = {c.label: c for c in comparisons}

    week_delta_pct = by_label["1 Week Ago"].pct_deltas.get("us_equity_score")
    longer_key, longer_delta_pct = _pick_longer_window(comparisons, "us_equity_score")
    longer_word = _WINDOW_WORD[lang][longer_key]

    if lang == "zh":
        status_zh = {"Healthy": "健康", "Caution": "谨慎", "Warning": "警示", "Emergency": "紧急"}.get(current.overall_status, current.overall_status)
        headline = (
            f"美股健康度为{current.us_equity_score:.1f}/10（{status_zh}），"
            f"较上周{_trend_phrase(week_delta_pct, lang)}，较上{longer_word}{_trend_phrase(longer_delta_pct, lang)}。"
        )
    else:
        headline = (
            f"U.S. Equity Health is {current.us_equity_score:.1f}/10 ({current.overall_status}), "
            f"{_trend_phrase(week_delta_pct, lang)} vs. last week and {_trend_phrase(longer_delta_pct, lang)} vs. last {longer_word}."
        )

    blocks = [
        _factor_block("overall", current.us_equity_score, "/10", comparisons, "us_equity_score", lang),
        _factor_block("credit_liquidity", (current.credit_score + current.liquidity_score) / 2, "/10", comparisons, "credit_score", lang),
        _factor_block("equity_internals", current.equity_internals_score, "/10", comparisons, "equity_internals_score", lang),
        _factor_block("macro", current.us_macro_score, "/10", comparisons, "us_macro_score", lang),
        _factor_block("global", current.global_score, "/10", comparisons, "global_score", lang),
        _factor_block("ai_funding", current.ai_funding_score, "/10", comparisons, "ai_funding_score", lang),
    ]

    if current.fear_greed_index is not None:
        blocks.append(_factor_block("sentiment", current.fear_greed_index, "/100", comparisons, "fear_greed_index", lang))

    if lang == "zh":
        breadth_sentences = [
            f"目前追踪范围内共有{red_count}个红色、{yellow_count}个黄色、{green_count}个绿色指标。",
            (f"今日有{emergency_count}条紧急级别警报 - 详见每日动态。" if emergency_count > 0 else "今日没有紧急级别警报。"),
            EQUITY_CONTEXT_ZH["breadth"],
        ]
    else:
        breadth_sentences = [
            f"Right now {red_count} indicators are red, {yellow_count} yellow, and {green_count} green across the tracked universe.",
            (
                f"{emergency_count} emergency-level alert(s) are active today - see the Daily Feed for details."
                if emergency_count > 0
                else "No emergency-level alerts are active today."
            ),
            EQUITY_CONTEXT_EN["breadth"],
        ]

    blocks.append(
        SummaryBlock(
            title=BLOCK_TITLES["breadth"][1] if lang == "zh" else BLOCK_TITLES["breadth"][0],
            tone="negative" if (red_count > green_count or emergency_count > 0) else "neutral",
            sentences=breadth_sentences,
        )
    )

    return headline, comparisons, blocks
