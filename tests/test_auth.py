from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.models import InviteCode, LoginEvent, User
from app.db.session import Base, get_db
from app.main import app
from app.security import create_access_token, decode_access_token, hash_password, verify_password


def _make_session_factory():
    # StaticPool + check_same_thread=False: FastAPI runs sync route handlers in a worker
    # thread, and SQLite's default per-thread :memory: pooling would otherwise hand that
    # thread a brand-new, empty database ("no such table: users").
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine, tables=[User.__table__, InviteCode.__table__, LoginEvent.__table__])
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
    admin = User(username="admin", password_hash=hash_password("admin-password"), role="admin")
    db.add(admin)
    db.commit()
    db.close()
    return TestClient(app), SessionLocal


def _teardown(client):
    app.dependency_overrides.clear()


def test_password_hash_round_trip():
    hashed = hash_password("correct horse battery staple")
    assert verify_password("correct horse battery staple", hashed)
    assert not verify_password("wrong password", hashed)


def test_token_round_trip():
    token = create_access_token(user_id=42, username="alice", role="user")
    payload = decode_access_token(token)
    assert payload is not None
    assert payload["sub"] == "42"
    assert payload["username"] == "alice"
    assert payload["role"] == "user"


def test_tampered_token_rejected():
    token = create_access_token(user_id=1, username="alice", role="user")
    assert decode_access_token(token + "tampered") is None


def _admin_headers(client: TestClient) -> dict:
    res = client.post("/api/auth/login", json={"username": "admin", "password": "admin-password"})
    assert res.status_code == 200
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


def test_register_with_valid_code_succeeds_and_consumes_it():
    client, SessionLocal = _make_client()
    try:
        headers = _admin_headers(client)
        code_res = client.post("/api/admin/invite-codes", json={"label": "for bob"}, headers=headers)
        assert code_res.status_code == 200
        code = code_res.json()["code"]

        reg_res = client.post("/api/auth/register", json={"code": code, "username": "bob", "password": "bob-password"})
        assert reg_res.status_code == 200
        assert reg_res.json()["user"]["username"] == "bob"

        reuse_res = client.post("/api/auth/register", json={"code": code, "username": "carol", "password": "carol-password"})
        assert reuse_res.status_code == 400
    finally:
        _teardown(client)


def test_register_with_unknown_code_fails():
    client, _ = _make_client()
    try:
        res = client.post("/api/auth/register", json={"code": "NOPE1234", "username": "eve", "password": "eve-password"})
        assert res.status_code == 400
    finally:
        _teardown(client)


def test_register_with_revoked_code_fails():
    client, _ = _make_client()
    try:
        headers = _admin_headers(client)
        code_res = client.post("/api/admin/invite-codes", json={}, headers=headers)
        invite_id = code_res.json()["id"]
        code = code_res.json()["code"]

        revoke_res = client.delete(f"/api/admin/invite-codes/{invite_id}", headers=headers)
        assert revoke_res.status_code == 200

        res = client.post("/api/auth/register", json={"code": code, "username": "dan", "password": "dan-password"})
        assert res.status_code == 400
    finally:
        _teardown(client)


def test_login_with_wrong_password_fails():
    client, _ = _make_client()
    try:
        res = client.post("/api/auth/login", json={"username": "admin", "password": "wrong"})
        assert res.status_code == 401
    finally:
        _teardown(client)


def test_protected_route_requires_token():
    client, _ = _make_client()
    try:
        res = client.get("/api/indicators")
        assert res.status_code == 401
    finally:
        _teardown(client)


def test_admin_route_forbidden_for_regular_user():
    client, _ = _make_client()
    try:
        headers = _admin_headers(client)
        code_res = client.post("/api/admin/invite-codes", json={}, headers=headers)
        code = code_res.json()["code"]
        reg_res = client.post("/api/auth/register", json={"code": code, "username": "regular", "password": "regular-password"})
        user_headers = {"Authorization": f"Bearer {reg_res.json()['access_token']}"}

        res = client.get("/api/admin/users", headers=user_headers)
        assert res.status_code == 403
    finally:
        _teardown(client)


def test_register_defaults_to_english_unconfirmed():
    client, _ = _make_client()
    try:
        headers = _admin_headers(client)
        code_res = client.post("/api/admin/invite-codes", json={}, headers=headers)
        code = code_res.json()["code"]
        reg_res = client.post("/api/auth/register", json={"code": code, "username": "newbie", "password": "newbie-password"})
        user = reg_res.json()["user"]
        assert user["language"] == "en"
        assert user["language_confirmed"] is False
    finally:
        _teardown(client)


def test_set_language_updates_user_and_reissues_token():
    client, _ = _make_client()
    try:
        headers = _admin_headers(client)
        res = client.patch("/api/auth/language", json={"language": "zh"}, headers=headers)
        assert res.status_code == 200
        body = res.json()
        assert body["user"]["language"] == "zh"
        assert body["user"]["language_confirmed"] is True
        claims = decode_access_token(body["access_token"])
        assert claims["language"] == "zh"
        assert claims["language_confirmed"] is True
    finally:
        _teardown(client)


def test_set_language_rejects_unknown_language():
    client, _ = _make_client()
    try:
        headers = _admin_headers(client)
        res = client.patch("/api/auth/language", json={"language": "fr"}, headers=headers)
        assert res.status_code == 400
    finally:
        _teardown(client)
