from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.models import (
    FavoriteIndicator,
    IndicatorDefinition,
    IndicatorObservation,
    IndicatorScore,
    InviteCode,
    LoginEvent,
    User,
)
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


def _seed_indicator(db, slug: str) -> int:
    defn = IndicatorDefinition(
        slug=slug, name=slug, category="credit_risk_appetite", subcategory="credit", source_id=None,
        connector_key="fred", series_identifier="X", frequency="daily", units="percent",
        health_polarity="lower_is_healthy", cluster="credit", active=True,
    )
    db.add(defn)
    db.commit()
    return defn.id


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
    user = User(username="favtester", password_hash=hash_password("fav-password"), role="user")
    db.add(user)
    db.commit()
    slugs = ["hy-oas", "ig-oas", "nfci"]
    ids = [_seed_indicator(db, s) for s in slugs]
    db.close()
    return TestClient(app), SessionLocal, slugs, ids


def _teardown(client):
    app.dependency_overrides.clear()


def _login_headers(client: TestClient) -> dict:
    res = client.post("/api/auth/login", json={"username": "favtester", "password": "fav-password"})
    assert res.status_code == 200
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


def test_favorites_start_empty():
    client, _, _, _ = _make_client()
    try:
        headers = _login_headers(client)
        res = client.get("/api/favorites", headers=headers)
        assert res.status_code == 200
        assert res.json() == []
    finally:
        _teardown(client)


def test_add_favorite_marks_card_as_favorited():
    client, _, slugs, _ = _make_client()
    try:
        headers = _login_headers(client)
        res = client.post(f"/api/favorites/{slugs[0]}", headers=headers)
        assert res.status_code == 200
        assert res.json()["is_favorited"] is True

        listed = client.get("/api/favorites", headers=headers)
        assert [c["slug"] for c in listed.json()] == [slugs[0]]

        cards = client.get("/api/indicators", headers=headers).json()
        favorited_slugs = {c["slug"] for c in cards if c["is_favorited"]}
        assert favorited_slugs == {slugs[0]}
    finally:
        _teardown(client)


def test_adding_same_favorite_twice_is_idempotent():
    client, _, slugs, _ = _make_client()
    try:
        headers = _login_headers(client)
        client.post(f"/api/favorites/{slugs[0]}", headers=headers)
        client.post(f"/api/favorites/{slugs[0]}", headers=headers)
        listed = client.get("/api/favorites", headers=headers).json()
        assert len(listed) == 1
    finally:
        _teardown(client)


def test_remove_favorite():
    client, _, slugs, _ = _make_client()
    try:
        headers = _login_headers(client)
        client.post(f"/api/favorites/{slugs[0]}", headers=headers)
        res = client.delete(f"/api/favorites/{slugs[0]}", headers=headers)
        assert res.status_code == 200
        listed = client.get("/api/favorites", headers=headers).json()
        assert listed == []
    finally:
        _teardown(client)


def test_reorder_favorites_persists_order():
    client, _, slugs, _ = _make_client()
    try:
        headers = _login_headers(client)
        for s in slugs:
            client.post(f"/api/favorites/{s}", headers=headers)

        reversed_order = list(reversed(slugs))
        res = client.put("/api/favorites/order", json={"slugs": reversed_order}, headers=headers)
        assert res.status_code == 200

        listed = client.get("/api/favorites", headers=headers).json()
        assert [c["slug"] for c in listed] == reversed_order
    finally:
        _teardown(client)


def test_favorites_are_scoped_per_user():
    client, SessionLocal, slugs, _ = _make_client()
    try:
        db = SessionLocal()
        other = User(username="otheruser", password_hash=hash_password("other-password"), role="user")
        db.add(other)
        db.commit()
        db.close()

        headers = _login_headers(client)
        client.post(f"/api/favorites/{slugs[0]}", headers=headers)

        other_login = client.post("/api/auth/login", json={"username": "otheruser", "password": "other-password"})
        other_headers = {"Authorization": f"Bearer {other_login.json()['access_token']}"}
        other_favorites = client.get("/api/favorites", headers=other_headers).json()
        assert other_favorites == []
    finally:
        _teardown(client)
