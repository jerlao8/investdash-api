from datetime import datetime

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.models import FavoriteIndicator, IndicatorDefinition, IndicatorObservation, IndicatorScore, InviteCode, LoginEvent, User
from app.db.session import Base, get_db
from app.main import app
from app.security import hash_password


def _make_session_factory():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(
        bind=engine,
        tables=[
            User.__table__, InviteCode.__table__, LoginEvent.__table__,
            IndicatorDefinition.__table__, IndicatorObservation.__table__, IndicatorScore.__table__,
            FavoriteIndicator.__table__,
        ],
    )
    return sessionmaker(bind=engine)


def _make_client():
    SessionLocal = _make_session_factory()

    def override_get_db():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    db = SessionLocal()
    user = User(username="indtester", password_hash=hash_password("ind-password"), role="user")
    db.add(user)
    db.commit()
    db.close()
    return TestClient(app), SessionLocal


def _teardown(client):
    app.dependency_overrides.clear()


def _login_headers(client: TestClient) -> dict:
    res = client.post("/api/auth/login", json={"username": "indtester", "password": "ind-password"})
    assert res.status_code == 200
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


def test_indicator_with_score_but_no_observation_is_marked_stale():
    """Regression test: a score row whose observation_id doesn't resolve to a real,
    current observation for this indicator (e.g. a dangling/mismatched foreign key from a
    corrupted pipeline run) must never be shown as fresh - is_stale should be True even
    though the score's own color_state is a "healthy-looking" non-gray value."""
    client, SessionLocal = _make_client()
    try:
        headers = _login_headers(client)
        db = SessionLocal()
        defn = IndicatorDefinition(
            slug="orphan-score", name="Orphan Score", category="credit_risk_appetite", subcategory="credit",
            source_id=None, connector_key="fred", series_identifier="X", frequency="daily", units="percent",
            health_polarity="lower_is_healthy", cluster="credit", active=True,
        )
        db.add(defn)
        db.commit()
        # No IndicatorObservation row exists for this indicator at all - simulates the case
        # where a score references an observation_id (e.g. 999999) that doesn't belong to it.
        db.add(
            IndicatorScore(
                indicator_id=defn.id, observation_id=999999, health_score_0_100=50.0, stress_percentile=72.7,
                z_score=0.6, velocity_score=51.6, persistence_score=100.0, color_state="yellow",
                direction="positive", raw_trend="down", confidence=100.0, calculated_at=datetime.utcnow(),
            )
        )
        db.commit()
        db.close()

        res = client.get("/api/indicators", headers=headers)
        assert res.status_code == 200
        card = next(c for c in res.json() if c["slug"] == "orphan-score")
        assert card["current_value"] is None
        assert card["last_observation_date"] is None
        assert card["is_stale"] is True
    finally:
        _teardown(client)


def test_indicator_with_matching_observation_is_not_stale():
    client, SessionLocal = _make_client()
    try:
        headers = _login_headers(client)
        db = SessionLocal()
        defn = IndicatorDefinition(
            slug="healthy-indicator", name="Healthy Indicator", category="credit_risk_appetite", subcategory="credit",
            source_id=None, connector_key="fred", series_identifier="X", frequency="daily", units="percent",
            health_polarity="lower_is_healthy", cluster="credit", active=True,
        )
        db.add(defn)
        db.commit()
        obs = IndicatorObservation(indicator_id=defn.id, observation_date=datetime.utcnow().date(), value=1.0)
        db.add(obs)
        db.commit()
        db.add(
            IndicatorScore(
                indicator_id=defn.id, observation_id=obs.id, health_score_0_100=80.0, stress_percentile=20.0,
                z_score=-0.5, velocity_score=60.0, persistence_score=100.0, color_state="green",
                direction="positive", raw_trend="up", confidence=100.0, calculated_at=datetime.utcnow(),
            )
        )
        db.commit()
        db.close()

        res = client.get("/api/indicators", headers=headers)
        assert res.status_code == 200
        card = next(c for c in res.json() if c["slug"] == "healthy-indicator")
        assert card["is_stale"] is False
        assert card["current_value"] == 1.0
    finally:
        _teardown(client)
