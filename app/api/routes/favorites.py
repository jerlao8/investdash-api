from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_extreme_ranges_since, get_lang, get_latest_observations, get_latest_scores
from app.api.routes.indicators import _card
from app.db.models import FavoriteIndicator, IndicatorDefinition, User
from app.db.session import get_db
from app.schemas.favorites import ReorderFavoritesRequest
from app.schemas.responses import IndicatorCard
from app.scoring.extremes import LAST_RECESSION_START

router = APIRouter()


@router.get("/favorites", response_model=list[IndicatorCard])
def list_favorites(db: Session = Depends(get_db), lang: str = Depends(get_lang), user: User = Depends(get_current_user)) -> list[IndicatorCard]:
    favorites = (
        db.query(FavoriteIndicator)
        .filter(FavoriteIndicator.user_id == user.id)
        .order_by(FavoriteIndicator.position.asc())
        .all()
    )
    if not favorites:
        return []

    defs_by_id = {d.id: d for d in db.query(IndicatorDefinition).filter(IndicatorDefinition.id.in_([f.indicator_id for f in favorites])).all()}
    obs_map = get_latest_observations(db)
    score_map = get_latest_scores(db)
    extreme_ranges = get_extreme_ranges_since(db, LAST_RECESSION_START)
    favorited_ids = frozenset(f.indicator_id for f in favorites)

    cards: list[IndicatorCard] = []
    for f in favorites:
        defn = defs_by_id.get(f.indicator_id)
        if defn is None:
            continue  # indicator was deleted/deactivated since favoriting - skip rather than error
        cards.append(_card(defn, obs_map.get(defn.id), score_map.get(defn.id), db, lang, extreme_ranges.get(defn.id), favorited_ids))
    return cards


@router.post("/favorites/{slug}", response_model=IndicatorCard)
def add_favorite(slug: str, db: Session = Depends(get_db), lang: str = Depends(get_lang), user: User = Depends(get_current_user)) -> IndicatorCard:
    defn = db.query(IndicatorDefinition).filter(IndicatorDefinition.slug == slug).first()
    if defn is None:
        raise HTTPException(status_code=404, detail="indicator not found")

    existing = db.query(FavoriteIndicator).filter(FavoriteIndicator.user_id == user.id, FavoriteIndicator.indicator_id == defn.id).first()
    if existing is None:
        max_position = db.query(FavoriteIndicator).filter(FavoriteIndicator.user_id == user.id).count()
        db.add(FavoriteIndicator(user_id=user.id, indicator_id=defn.id, position=max_position))
        db.commit()

    obs_map = get_latest_observations(db)
    score_map = get_latest_scores(db)
    extreme_ranges = get_extreme_ranges_since(db, LAST_RECESSION_START)
    return _card(defn, obs_map.get(defn.id), score_map.get(defn.id), db, lang, extreme_ranges.get(defn.id), frozenset({defn.id}))


@router.delete("/favorites/{slug}")
def remove_favorite(slug: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    defn = db.query(IndicatorDefinition).filter(IndicatorDefinition.slug == slug).first()
    if defn is None:
        raise HTTPException(status_code=404, detail="indicator not found")
    db.query(FavoriteIndicator).filter(FavoriteIndicator.user_id == user.id, FavoriteIndicator.indicator_id == defn.id).delete()
    db.commit()
    return {"removed": True}


@router.put("/favorites/order")
def reorder_favorites(payload: ReorderFavoritesRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    slug_to_id = {
        d.slug: d.id
        for d in db.query(IndicatorDefinition).filter(IndicatorDefinition.slug.in_(payload.slugs)).all()
    }
    favorites_by_indicator = {
        f.indicator_id: f
        for f in db.query(FavoriteIndicator).filter(FavoriteIndicator.user_id == user.id).all()
    }
    for position, slug in enumerate(payload.slugs):
        indicator_id = slug_to_id.get(slug)
        favorite = favorites_by_indicator.get(indicator_id) if indicator_id else None
        if favorite is not None:
            favorite.position = position
    db.commit()
    return {"reordered": True}
