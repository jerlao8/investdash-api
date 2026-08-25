from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import (
    compute_changes,
    get_current_user,
    get_extreme_range_for,
    get_extreme_ranges_since,
    get_favorited_indicator_ids,
    get_lang,
    get_latest_observation_for,
    get_latest_observations,
    get_latest_score_for,
    get_latest_scores,
)
from app.db.models import IndicatorDefinition, IndicatorObservation, IndicatorScore, User
from app.db.session import get_db
from app.schemas.responses import IndicatorCard, IndicatorDetail, IndicatorHistoryPoint
from app.scoring.extremes import LAST_RECESSION_START, extreme_flag
from app.scoring.health_score import reading_guide as _generic_reading_guide
from app.timeutil import today_pt

router = APIRouter()

RANGE_DAYS = {"1M": 31, "3M": 92, "1Y": 366, "3Y": 1096, "5Y": 1827, "10Y": 3653}


def _source_updated_today(obs: IndicatorObservation | None, now: datetime | None = None) -> bool:
    """True when the latest data point's as-of date is today (PT) — not when we last pulled."""
    if obs is None or obs.observation_date is None:
        return False
    return obs.observation_date == today_pt(now)


def _card(
    defn: IndicatorDefinition,
    obs: IndicatorObservation | None,
    score: IndicatorScore | None,
    db: Session,
    lang: str = "en",
    extreme_range: tuple[float, float] | None = None,
    favorited_ids: frozenset[int] = frozenset(),
) -> IndicatorCard:
    change_1d = change_5d = change_1m = None
    if obs is not None:
        change_1d, change_5d, change_1m = compute_changes(db, defn.id)

    extreme_kind = extreme_tone = None
    if obs is not None and extreme_range is not None:
        extreme_kind, extreme_tone = extreme_flag(obs.value, extreme_range[0], extreme_range[1], defn.health_polarity)

    is_zh = lang == "zh"
    name = (defn.name_zh if is_zh else "") or defn.name
    info_text = (defn.info_text_zh if is_zh else "") or defn.info_text
    reading_guide = (defn.reading_guide_zh if is_zh else "") or defn.reading_guide or _generic_reading_guide(defn.health_polarity, lang)

    return IndicatorCard(
        slug=defn.slug, name=name, category=defn.category, subcategory=defn.subcategory, cluster=defn.cluster,
        frequency=defn.frequency, units=defn.units, lead_lag=defn.lead_lag, crisis_relevance=defn.crisis_relevance,
        is_critical=defn.is_critical, is_favorited=defn.id in favorited_ids, current_value=obs.value if obs else None,
        color_state=score.color_state if score else "gray", direction=score.direction if score else "flat",
        raw_trend=score.raw_trend if score else "flat",
        stress_percentile=score.stress_percentile if score else None,
        health_score=score.health_score_0_100 if score else None,
        change_1d=change_1d, change_5d=change_5d, change_1m=change_1m,
        last_observation_date=obs.observation_date if obs else None,
        source_updated_today=_source_updated_today(obs),
        confidence=score.confidence if score else None,
        # A score row can in principle outlive/mismatch the observation it was computed from
        # (e.g. a corrupted or orphaned observation_id) - never show an indicator as "fresh"
        # (a confident color/score) when there's no actual current observation behind it.
        is_stale=True if obs is None or score is None else (score.color_state == "gray"),
        info_text=info_text, health_polarity=defn.health_polarity,
        reading_guide=reading_guide,
        extreme_kind=extreme_kind, extreme_since=LAST_RECESSION_START if extreme_kind else None, extreme_tone=extreme_tone,
        source_name=defn.source_name, source_url=defn.source_url or (obs.source_url if obs else ""),
    )


@router.get("/indicators", response_model=list[IndicatorCard])
def list_indicators(
    db: Session = Depends(get_db),
    lang: str = Depends(get_lang),
    user: User = Depends(get_current_user),
    category: str | None = None,
    cluster: str | None = None,
    state: str | None = None,
    search: str | None = None,
    critical_only: bool = False,
    sort: str | None = None,
) -> list[IndicatorCard]:
    q = db.query(IndicatorDefinition).filter(IndicatorDefinition.active == True)  # noqa: E712
    if category:
        q = q.filter(IndicatorDefinition.category == category)
    if cluster:
        q = q.filter(IndicatorDefinition.cluster == cluster)
    if critical_only:
        q = q.filter(IndicatorDefinition.is_critical == True)  # noqa: E712
    if search:
        like = f"%{search.lower()}%"
        q = q.filter(
            (IndicatorDefinition.name.ilike(like))
            | (IndicatorDefinition.category.ilike(like))
            | (IndicatorDefinition.info_text.ilike(like))
        )
    definitions = q.all()

    obs_map = get_latest_observations(db)
    score_map = get_latest_scores(db)
    extreme_ranges = get_extreme_ranges_since(db, LAST_RECESSION_START)
    favorited_ids = frozenset(get_favorited_indicator_ids(db, user.id))

    cards = [_card(d, obs_map.get(d.id), score_map.get(d.id), db, lang, extreme_ranges.get(d.id), favorited_ids) for d in definitions]
    if state:
        cards = [c for c in cards if c.color_state == state]
    if sort == "stress":
        cards.sort(key=lambda c: c.stress_percentile or 0, reverse=True)
    elif sort == "name":
        cards.sort(key=lambda c: c.name)
    return cards


@router.get("/indicators/history/batch", response_model=dict[str, list[IndicatorHistoryPoint]])
def get_indicator_history_batch(
    slugs: str = Query(..., description="comma-separated indicator slugs"),
    range: str = Query("3M"),
    db: Session = Depends(get_db),
) -> dict[str, list[IndicatorHistoryPoint]]:
    """Batched history lookup so callers needing several small series (e.g. hover trendlines
    for a handful of movers) don't have to make one round trip per indicator."""
    slug_list = [s for s in slugs.split(",") if s]
    definitions = db.query(IndicatorDefinition).filter(IndicatorDefinition.slug.in_(slug_list)).all()
    id_to_slug = {d.id: d.slug for d in definitions}
    if not id_to_slug:
        return {}

    q = db.query(IndicatorObservation).filter(IndicatorObservation.indicator_id.in_(id_to_slug.keys()))
    if range != "Max":
        days = RANGE_DAYS.get(range, 92)
        q = q.filter(IndicatorObservation.observation_date >= today_pt() - timedelta(days=days))
    rows = q.order_by(IndicatorObservation.observation_date.asc()).all()

    out: dict[str, list[IndicatorHistoryPoint]] = {slug: [] for slug in id_to_slug.values()}
    for r in rows:
        out[id_to_slug[r.indicator_id]].append(IndicatorHistoryPoint(date=r.observation_date, value=r.value))
    return out


@router.get("/indicators/{slug}", response_model=IndicatorDetail)
def get_indicator(
    slug: str,
    range: str = Query("1Y"),
    db: Session = Depends(get_db),
    lang: str = Depends(get_lang),
    user: User = Depends(get_current_user),
) -> IndicatorDetail:
    defn = db.query(IndicatorDefinition).filter(IndicatorDefinition.slug == slug).first()
    if defn is None:
        raise HTTPException(status_code=404, detail="indicator not found")

    obs = get_latest_observation_for(db, defn.id)
    score = get_latest_score_for(db, defn.id)
    extreme_range = get_extreme_range_for(db, defn.id, LAST_RECESSION_START)
    favorited_ids = frozenset(get_favorited_indicator_ids(db, user.id))
    card = _card(defn, obs, score, db, lang, extreme_range, favorited_ids)

    q = db.query(IndicatorObservation).filter(IndicatorObservation.indicator_id == defn.id)
    if range != "Max":
        days = RANGE_DAYS.get(range, 366)
        q = q.filter(IndicatorObservation.observation_date >= today_pt() - timedelta(days=days))
    rows = q.order_by(IndicatorObservation.observation_date.asc()).all()

    history = [IndicatorHistoryPoint(date=r.observation_date, value=r.value) for r in rows]
    return IndicatorDetail(card=card, history=history)
