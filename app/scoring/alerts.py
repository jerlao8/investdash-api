"""Alert levels, clustering/dedupe, and Daily Feed generation (PRD Sections 30-33).

All prose is template-generated from structured data (cluster, direction, percentile,
change) - no LLM calls, per Section 30's "never let an LLM invent the raw value or source"
and this build's decision to keep scoring/alerting fully deterministic.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from app.scoring.aggregate import ScoredIndicator

CREDIT_LIQUIDITY_CLUSTERS = {"credit", "liquidity", "banking"}
EQUITY_VOL_CLUSTERS = {"equity_breadth", "volatility_options"}

CLUSTER_LABELS = {
    "credit": "Credit",
    "liquidity": "Liquidity",
    "banking": "Banking",
    "labor": "Labor",
    "growth": "Growth",
    "inflation": "Inflation",
    "rates": "Rates",
    "equity_breadth": "Equity Breadth",
    "volatility_options": "Options/Volatility",
    "valuation": "Valuation",
    "sentiment_positioning": "Sentiment/Positioning",
    "global_fx_liquidity": "Global FX/Liquidity",
    "ai_semiconductor": "AI/Semiconductor",
}

CLUSTER_LABELS_ZH = {
    "credit": "信贷",
    "liquidity": "流动性",
    "banking": "银行业",
    "labor": "就业",
    "growth": "增长",
    "inflation": "通胀",
    "rates": "利率",
    "equity_breadth": "股票广度",
    "volatility_options": "期权/波动率",
    "valuation": "估值",
    "sentiment_positioning": "情绪/仓位",
    "global_fx_liquidity": "全球外汇/流动性",
    "ai_semiconductor": "AI/半导体",
}

CATEGORY_IMPLICATION = {
    "credit_risk_appetite": "Wider credit spreads indicate tighter corporate funding conditions and can pressure equity risk appetite, especially when accompanied by weaker breadth.",
    "banking_credit_creation": "Tightening bank lending standards or slowing loan growth signals reduced credit creation, a historical precursor to slower growth and equity multiple compression.",
    "liquidity_funding": "Deteriorating funding/liquidity conditions raise the cost and difficulty of financing risk assets, a key transmission channel into equity drawdowns.",
    "equity_breadth_internals": "Narrowing breadth means fewer stocks are participating in market strength, often masking underlying fragility in the index level.",
    "volatility_options": "Rising volatility/options stress reflects deteriorating risk appetite and can precede or accompany broader equity selloffs.",
    "macro_growth": "Slowing growth indicators raise recession risk, which historically pressures corporate earnings and equity valuations.",
    "macro_labor": "Labor market deterioration is a classic recession-transmission signal and tends to lead broader economic weakness.",
    "macro_inflation": "Inflation dynamics shift the policy-rate path, which feeds directly into discount rates and equity valuations.",
    "macro_fiscal": "Sovereign funding stress can compete with private-sector liquidity and pressure term premia.",
    "macro_rates": "Yield-curve and rate moves reprice the risk-free rate used across all equity valuation models.",
    "valuation": "Elevated valuation alone rarely times a correction, but it amplifies downside when liquidity or credit also deteriorate.",
    "sentiment_positioning": "Extreme positioning increases the risk of forced de-risking if conditions turn, amplifying moves in either direction.",
    "global_liquidity": "Global liquidity conditions transmit into U.S. dollar funding costs and cross-border risk appetite.",
    "global_fx": "Dollar strength tightens financial conditions globally, especially for dollar-denominated borrowers.",
    "global_growth": "Slowing global growth can spill over into U.S. corporate revenue and risk sentiment.",
    "global_inflation_rates": "Diverging global inflation/rate paths affect capital flows and relative equity performance.",
    "global_equities": "Widening global equity weakness raises the odds that U.S. equities are not immune to the same pressures.",
    "global_commodities": "Commodity stress is a real-economy signal that can precede broader growth or inflation surprises.",
    "ai_funding": "AI infrastructure funding stress raises the risk that current AI capex plans outrun the financing available to sustain them.",
    "ai_demand": "Semiconductor/AI demand deceleration raises questions about whether current AI infrastructure valuations are supported by underlying end demand.",
}

# Positive-direction counterparts - equity_implication must explain the actual direction of the
# move, not always read as a deterioration warning (Section 33: the feed must not be a doom
# machine; a tightening HY spread and a widening one need different explanatory text).
CATEGORY_IMPLICATION_POSITIVE = {
    "credit_risk_appetite": "Tighter credit spreads signal easier corporate funding conditions, typically supportive of equity risk appetite.",
    "banking_credit_creation": "Easing lending standards or accelerating loan growth signals healthier credit creation, supportive of growth and equity multiples.",
    "liquidity_funding": "Improving funding/liquidity conditions lower the cost of financing risk assets, a supportive channel for equity valuations.",
    "equity_breadth_internals": "Broadening participation means more stocks are confirming market strength - a healthier foundation than narrow, concentrated gains.",
    "volatility_options": "Falling volatility/options stress reflects improving risk appetite and is typically supportive of continued equity gains.",
    "macro_growth": "Accelerating growth indicators lower recession risk, which typically supports corporate earnings and equity valuations.",
    "macro_labor": "Labor market strength supports consumer spending and reduces near-term recession risk.",
    "macro_inflation": "Cooling, well-behaved inflation gives the Fed more room to ease, generally supportive of equity valuations via lower discount rates.",
    "macro_fiscal": "Easing sovereign funding pressure reduces competition for private-sector liquidity.",
    "macro_rates": "Favorable yield-curve or rate moves can lower the discount rate used across equity valuation models.",
    "valuation": "Improving valuation metrics reduce one source of fragility, though they remain secondary to liquidity and credit.",
    "sentiment_positioning": "Positioning normalizing from an extreme reduces the risk of a forced, disorderly unwind.",
    "global_liquidity": "Improving global liquidity conditions ease U.S. dollar funding costs and support cross-border risk appetite.",
    "global_fx": "A more stable or weaker dollar eases financial conditions globally, especially for dollar-denominated borrowers.",
    "global_growth": "Accelerating global growth can lift U.S. corporate revenue and broader risk sentiment.",
    "global_inflation_rates": "Stabilizing global inflation/rate paths support capital flows and relative equity performance.",
    "global_equities": "Broadening global equity strength is a supportive signal that risk appetite extends beyond the U.S. alone.",
    "global_commodities": "Commodity stability is a real-economy signal consistent with steady growth and inflation.",
    "ai_funding": "Easing AI infrastructure funding stress supports continued capex without forcing dilutive financing or credit deterioration.",
    "ai_demand": "Accelerating semiconductor/AI demand supports the case that current AI infrastructure valuations are backed by real end demand.",
}

CATEGORY_IMPLICATION_ZH = {
    "credit_risk_appetite": "信用利差走阔表明企业融资环境收紧，可能打压股票风险偏好，尤其是在市场广度同时走弱的情况下。",
    "banking_credit_creation": "银行放贷标准收紧或贷款增速放缓意味着信贷创造减少，历史上这是增长放缓和股票估值倍数压缩的前兆。",
    "liquidity_funding": "流动性/融资状况恶化会提高为风险资产融资的成本与难度，是传导至股市回调的关键渠道。",
    "equity_breadth_internals": "广度收窄意味着参与市场走强的个股减少，往往掩盖了指数层面的潜在脆弱性。",
    "volatility_options": "波动率/期权压力上升反映风险偏好恶化，可能预示或伴随更广泛的股市抛售。",
    "macro_growth": "增长指标放缓会提高衰退风险，历史上会打压企业盈利和股票估值。",
    "macro_labor": "劳动力市场恶化是经典的衰退传导信号，往往领先于更广泛的经济走弱。",
    "macro_inflation": "通胀走势会改变政策利率路径，直接影响贴现率和股票估值。",
    "macro_fiscal": "主权融资压力可能与私营部门争夺流动性，并推高期限溢价。",
    "macro_rates": "收益率曲线和利率变动会重新定价所有股票估值模型所使用的无风险利率。",
    "valuation": "估值偏高本身很少能精准预示回调时点，但当流动性或信贷同时恶化时会放大下行风险。",
    "sentiment_positioning": "极端仓位增加了在市场转向时被迫去风险的可能性，从而放大双向波动。",
    "global_liquidity": "全球流动性状况会传导至美元融资成本和跨境风险偏好。",
    "global_fx": "美元走强会收紧全球金融条件，对以美元计价的借款人影响尤为明显。",
    "global_growth": "全球增长放缓可能波及美国企业营收和整体风险情绪。",
    "global_inflation_rates": "全球通胀/利率路径的分化会影响资本流动和股市相对表现。",
    "global_equities": "全球股市走弱范围扩大，增加了美股难以独善其身的可能性。",
    "global_commodities": "大宗商品承压是实体经济信号，可能预示更广泛的增长或通胀意外。",
    "ai_funding": "AI基础设施融资压力增加了当前AI资本开支计划可能超出可获得融资能力的风险。",
    "ai_demand": "半导体/AI需求放缓引发对当前AI基础设施估值是否有真实终端需求支撑的质疑。",
}

CATEGORY_IMPLICATION_POSITIVE_ZH = {
    "credit_risk_appetite": "信用利差收窄表明企业融资环境改善，通常有利于股票风险偏好。",
    "banking_credit_creation": "放贷标准放松或贷款增速加快意味着信贷创造更健康，利好增长和股票估值倍数。",
    "liquidity_funding": "流动性/融资状况改善降低了为风险资产融资的成本，是支撑股票估值的有利渠道。",
    "equity_breadth_internals": "参与度扩大意味着更多个股确认市场走强——相比集中且狭窄的涨幅，这是更健康的基础。",
    "volatility_options": "波动率/期权压力下降反映风险偏好改善，通常有利于股市延续涨势。",
    "macro_growth": "增长指标加速会降低衰退风险，通常支撑企业盈利和股票估值。",
    "macro_labor": "劳动力市场强劲支撑消费支出，降低短期衰退风险。",
    "macro_inflation": "通胀降温且趋于温和，为美联储提供更多宽松空间，通过降低贴现率利好股票估值。",
    "macro_fiscal": "主权融资压力缓解，减少了与私营部门对流动性的争夺。",
    "macro_rates": "有利的收益率曲线或利率变动可能降低股票估值模型所使用的贴现率。",
    "valuation": "估值指标改善减少了一个脆弱性来源，不过其重要性仍次于流动性和信贷。",
    "sentiment_positioning": "仓位从极端水平回归正常，降低了被迫无序平仓的风险。",
    "global_liquidity": "全球流动性状况改善缓解了美元融资成本，支撑跨境风险偏好。",
    "global_fx": "美元走势更稳定或走弱，缓解全球金融条件，对以美元计价的借款人尤为有利。",
    "global_growth": "全球增长加速可能提振美国企业营收和整体风险情绪。",
    "global_inflation_rates": "全球通胀/利率路径趋于稳定，支撑资本流动和股市相对表现。",
    "global_equities": "全球股市走强范围扩大，是风险偏好不止局限于美国的利好信号。",
    "global_commodities": "大宗商品保持稳定，是与稳健增长和温和通胀相符的实体经济信号。",
    "ai_funding": "AI基础设施融资压力缓解，支撑资本开支持续推进，无需被迫采取稀释性融资或承受信贷恶化。",
    "ai_demand": "半导体/AI需求加速，支持当前AI基础设施估值有真实终端需求支撑的判断。",
}


@dataclass
class ObservationContext:
    slug: str
    name: str
    name_zh: str
    value: float
    change_1d: float | None
    change_5d: float | None
    change_1m: float | None
    source_url: str
    source_name: str


def indicator_alert_level(scored: ScoredIndicator) -> str:
    """info | warning | red, per Section 31 Levels 1-3 (Level 4 Emergency is aggregate-only)."""
    z = abs(scored.components.z_score)
    if scored.stress_percentile > 90 or z > 2.0:
        return "red"
    if scored.color == "yellow" or scored.stress_percentile > 80 or z > 1.5:
        return "warning"
    return "info"


def detect_emergency(scored: list[ScoredIndicator]) -> tuple[bool, list[str]]:
    """Section 31 Level 4: >=3 independent clusters deteriorating, with at least one
    Credit/Funding-or-Liquidity cluster and at least one Equity Internals/Volatility cluster."""
    by_cluster: dict[str, list[ScoredIndicator]] = defaultdict(list)
    for s in scored:
        by_cluster[s.cluster].append(s)

    deteriorating: list[str] = []
    for cluster, members in by_cluster.items():
        non_stale = [m for m in members if not m.is_stale]
        if not non_stale:
            continue
        bad = [m for m in non_stale if m.color in ("yellow", "red") and m.components.velocity < 50]
        if len(bad) / len(non_stale) >= 0.5:
            deteriorating.append(cluster)

    has_credit_liq = any(c in CREDIT_LIQUIDITY_CLUSTERS for c in deteriorating)
    has_equity_vol = any(c in EQUITY_VOL_CLUSTERS for c in deteriorating)
    is_emergency = len(deteriorating) >= 3 and has_credit_liq and has_equity_vol
    return is_emergency, deteriorating


def _implication(category: str, direction: str, lang: str) -> str:
    if lang == "zh":
        table = CATEGORY_IMPLICATION_POSITIVE_ZH if direction == "positive" else CATEGORY_IMPLICATION_ZH
        default = (
            "此变动可能与仪表盘从流动性到信贷再到股市这一因果链条上的其他利好信号相互印证。"
            if direction == "positive"
            else "此变动可能与仪表盘从流动性到信贷再到股市这一因果链条上的其他压力信号相互印证或相互抵消。"
        )
        return table.get(category, default)

    table = CATEGORY_IMPLICATION_POSITIVE if direction == "positive" else CATEGORY_IMPLICATION
    default = (
        "This move can support other favorable signals across the dashboard's causal chain from liquidity to credit to equities."
        if direction == "positive"
        else "This move can corroborate or offset other stress signals across the dashboard's causal chain from liquidity to credit to equities."
    )
    return table.get(category, default)


def _emergency_item(deteriorating_clusters: list[str], feed_date) -> dict:
    cluster_names_en = ", ".join(CLUSTER_LABELS.get(c, c) for c in deteriorating_clusters)
    cluster_names_zh = "、".join(CLUSTER_LABELS_ZH.get(c, c) for c in deteriorating_clusters)
    n = len(deteriorating_clusters)
    return {
        "severity": "emergency",
        "event_type": "corroborated_deterioration",
        "cluster": "multiple",
        "indicator": None,
        "headline": f"EMERGENCY — {n} independent clusters deteriorated together",
        "headline_zh": f"紧急 — {n}个独立板块同步恶化",
        "summary": (
            f"Independent deterioration across {cluster_names_en} has occurred together, including at least "
            "one credit/liquidity cluster and one equity internals/volatility cluster. This corroboration "
            "across unrelated data sources is the dashboard's highest-confidence stress signal."
        ),
        "summary_zh": (
            f"{cluster_names_zh}等板块同时出现独立恶化，其中至少包含一个信贷/流动性板块和一个股票内部结构/波动率板块。"
            "来自不相关数据源的这种相互印证，是本仪表盘可信度最高的压力信号。"
        ),
        "equity_implication": "Elevated risk of a correction or sharper equity drawdown given multiple independent, corroborating deterioration signals.",
        "equity_implication_zh": "鉴于多个独立且相互印证的恶化信号同时出现，市场发生回调或更剧烈下跌的风险上升。",
        "source_urls": [],
        "source_name": "InvestDash aggregate",
        "dedupe_key": f"EMERGENCY_{feed_date.isoformat()}",
        "priority": 1,
        "category": "Emergency",
        "category_zh": "紧急",
        "direction": "negative",
    }


def build_feed_items(
    scored: list[ScoredIndicator],
    contexts: dict[str, ObservationContext],
    feed_date,
) -> list[dict]:
    """Returns feed-item dicts matching Section 30's JSON shape, clustered/deduped per
    Section 32, with positive signals per Section 33. Each item carries both English and
    Chinese renderings (`headline`/`headline_zh`, etc.) - this runs once per pipeline run and
    the result is stored, so both languages are computed now rather than regenerated later."""
    items: list[dict] = []

    is_emergency, deteriorating_clusters = detect_emergency(scored)
    if is_emergency:
        items.append(_emergency_item(deteriorating_clusters, feed_date))

    negative: dict[str, list[ScoredIndicator]] = defaultdict(list)
    positive: dict[str, list[ScoredIndicator]] = defaultdict(list)
    for s in scored:
        if s.is_stale:
            continue
        level = indicator_alert_level(s)
        worsening = s.components.velocity < 40
        improving = s.components.velocity > 60
        if level in ("warning", "red") and worsening:
            negative[s.cluster].append(s)
        elif s.health_score >= 65 and improving:
            positive[s.cluster].append(s)

    def emit_cluster(cluster: str, members: list[ScoredIndicator], polarity: str):
        label = CLUSTER_LABELS.get(cluster, cluster.title())
        label_zh = CLUSTER_LABELS_ZH.get(cluster, label)
        severities = [indicator_alert_level(m) for m in members]
        severity = "red" if "red" in severities else ("warning" if "warning" in severities else "info")
        clustered = len(members) >= 2
        headline = (
            f"{label} Stress Cluster Intensifies" if polarity == "negative" and clustered
            else f"{label} Conditions Improve" if polarity == "positive" and clustered
            else None
        )
        headline_zh = (
            f"{label_zh}压力板块加剧" if polarity == "negative" and clustered
            else f"{label_zh}状况改善" if polarity == "positive" and clustered
            else None
        )
        for m in members:
            ctx = contexts.get(m.slug)
            if ctx is None:
                continue
            dedupe_key = f"{m.slug}_{feed_date.isoformat()}"
            direction = "negative" if polarity == "negative" else "positive"
            name_zh = ctx.name_zh or ctx.name

            summary_lead = headline or f"{ctx.name} moved {'adversely' if polarity=='negative' else 'favorably'}"
            summary_lead_zh = headline_zh or f"{name_zh} 走势{'不利' if polarity=='negative' else '有利'}"

            if ctx.change_1d is not None:
                summary_en = f"{ctx.name} is at {ctx.value:g} ({m.stress_percentile:.0f}th stress percentile), 1D change {ctx.change_1d:+.2f}"
                summary_zh = f"{name_zh}目前为{ctx.value:g}（处于历史压力的第{m.stress_percentile:.0f}百分位），1日变化{ctx.change_1d:+.2f}"
            else:
                summary_en = f"{ctx.name} is at {ctx.value:g}."
                summary_zh = f"{name_zh}目前为{ctx.value:g}。"

            items.append(
                {
                    "severity": severity if polarity == "negative" else "info",
                    "event_type": "rapid_deterioration" if polarity == "negative" else "improvement",
                    "cluster": cluster,
                    "indicator": ctx.name,
                    "headline": f"{summary_lead}: {ctx.name}" if not headline else headline,
                    "headline_zh": f"{summary_lead_zh}：{name_zh}" if not headline_zh else headline_zh,
                    "summary": summary_en,
                    "summary_zh": summary_zh,
                    "equity_implication": _implication(m.category, direction, "en"),
                    "equity_implication_zh": _implication(m.category, direction, "zh"),
                    "source_urls": [ctx.source_url] if ctx.source_url else [],
                    "source_name": ctx.source_name,
                    "dedupe_key": dedupe_key,
                    "priority": 2 if polarity == "negative" else 4,
                    "category": label,
                    "category_zh": label_zh,
                    "value": ctx.value,
                    "change_1d": ctx.change_1d,
                    "change_5d": ctx.change_5d,
                    "historical_percentile": m.stress_percentile,
                    "health_state": m.color,
                    "direction": direction,
                }
            )

    for cluster, members in negative.items():
        emit_cluster(cluster, members, "negative")
    for cluster, members in positive.items():
        emit_cluster(cluster, members, "positive")

    return items
