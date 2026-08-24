from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.models import InviteCode, LoginEvent, User
from app.db.session import get_db
from app.schemas.auth import LoginRequest, RegisterRequest, SetLanguageRequest, TokenResponse, UserOut
from app.security import create_access_token, hash_password, verify_password

router = APIRouter()


def _user_out(user: User) -> UserOut:
    return UserOut(
        id=user.id, username=user.username, role=user.role, is_active=user.is_active,
        created_at=user.created_at, last_login_at=user.last_login_at, last_active_at=user.last_active_at,
        login_count=user.login_count, language=user.language, language_confirmed=user.language_confirmed,
    )


def _token_for(user: User) -> str:
    return create_access_token(user.id, user.username, user.role, user.language, user.language_confirmed)


def _log_event(db: Session, request: Request, user_id: int, event_type: str) -> None:
    db.add(
        LoginEvent(
            user_id=user_id, event_type=event_type,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
    )


@router.post("/auth/register", response_model=TokenResponse)
def register(payload: RegisterRequest, request: Request, db: Session = Depends(get_db)) -> TokenResponse:
    code = payload.code.strip()
    username = payload.username.strip()

    invite = db.query(InviteCode).filter(InviteCode.code == code).first()
    if invite is None or invite.revoked or invite.used_by_id is not None:
        raise HTTPException(status_code=400, detail="invalid, used, or revoked passcode")
    if not username or len(username) < 3:
        raise HTTPException(status_code=400, detail="username must be at least 3 characters")
    if len(payload.password) < 8:
        raise HTTPException(status_code=400, detail="password must be at least 8 characters")
    if db.query(User).filter(User.username == username).first() is not None:
        raise HTTPException(status_code=400, detail="username already taken")

    user = User(
        username=username, password_hash=hash_password(payload.password), role="user",
        invite_code_id=invite.id, last_login_at=datetime.utcnow(), last_active_at=datetime.utcnow(),
        login_count=1,
    )
    db.add(user)
    db.flush()

    invite.used_by_id = user.id
    invite.used_at = datetime.utcnow()
    _log_event(db, request, user.id, "register")
    db.commit()

    return TokenResponse(access_token=_token_for(user), user=_user_out(user))


@router.post("/auth/login", response_model=TokenResponse)
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)) -> TokenResponse:
    user = db.query(User).filter(User.username == payload.username.strip()).first()
    if user is None or not user.is_active or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="invalid username or password")

    user.last_login_at = datetime.utcnow()
    user.last_active_at = datetime.utcnow()
    user.login_count += 1
    _log_event(db, request, user.id, "login")
    db.commit()

    return TokenResponse(access_token=_token_for(user), user=_user_out(user))


@router.get("/auth/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)) -> UserOut:
    return _user_out(user)


@router.patch("/auth/language", response_model=TokenResponse)
def set_language(payload: SetLanguageRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> TokenResponse:
    if payload.language not in ("en", "zh"):
        raise HTTPException(status_code=400, detail="language must be 'en' or 'zh'")
    user.language = payload.language
    user.language_confirmed = True
    db.commit()
    # Reissue the token so the new language/confirmed claims take effect immediately, without
    # waiting for the existing 7-day token to expire.
    return TokenResponse(access_token=_token_for(user), user=_user_out(user))
