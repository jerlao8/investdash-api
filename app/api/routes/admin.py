from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.models import InviteCode, LoginEvent, User
from app.db.session import get_db
from app.jobs.cfi_pipeline import run_cfi_pipeline
from app.jobs.pipeline import run_full_pipeline
from app.schemas.auth import CreateInviteCodeRequest, InviteCodeOut, LoginEventOut, UpdatePasswordRequest, UpdateUserRequest, UserOut
from app.security import hash_password

router = APIRouter()


@router.post("/admin/recalculate")
def recalculate(db: Session = Depends(get_db)) -> dict:
    return run_full_pipeline(db)


@router.post("/admin/cfi/recalculate")
def cfi_recalculate(db: Session = Depends(get_db)) -> dict:
    return run_cfi_pipeline(db)


def _user_out(user: User) -> UserOut:
    return UserOut(
        id=user.id, username=user.username, role=user.role, is_active=user.is_active,
        created_at=user.created_at, last_login_at=user.last_login_at, last_active_at=user.last_active_at,
        login_count=user.login_count, language=user.language, language_confirmed=user.language_confirmed,
    )


def _invite_out(invite: InviteCode, usernames: dict[int, str]) -> InviteCodeOut:
    return InviteCodeOut(
        id=invite.id, code=invite.code, label=invite.label, created_at=invite.created_at,
        created_by=usernames.get(invite.created_by_id, "?"),
        used_by=usernames.get(invite.used_by_id) if invite.used_by_id else None,
        used_at=invite.used_at, revoked=invite.revoked,
    )


@router.get("/admin/users", response_model=list[UserOut])
def list_users(db: Session = Depends(get_db)) -> list[UserOut]:
    users = db.query(User).order_by(User.created_at.asc()).all()
    return [_user_out(u) for u in users]


@router.patch("/admin/users/{user_id}", response_model=UserOut)
def update_user(user_id: int, payload: UpdateUserRequest, db: Session = Depends(get_db), current: User = Depends(get_current_user)) -> UserOut:
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=404, detail="user not found")

    demoting_or_disabling = (payload.role is not None and payload.role != "admin") or payload.is_active is False
    if user.role == "admin" and demoting_or_disabling:
        if user.id == current.id:
            raise HTTPException(status_code=400, detail="cannot change your own admin status")
        remaining_admins = db.query(User).filter(User.role == "admin", User.id != user.id).count()
        if remaining_admins == 0:
            raise HTTPException(status_code=400, detail="cannot remove the last remaining admin")

    if payload.role is not None:
        if payload.role not in ("user", "admin"):
            raise HTTPException(status_code=400, detail="role must be 'user' or 'admin'")
        user.role = payload.role
    if payload.is_active is not None:
        user.is_active = payload.is_active

    db.commit()
    return _user_out(user)


@router.patch("/admin/users/{user_id}/password")
def update_user_password(user_id: int, payload: UpdatePasswordRequest, db: Session = Depends(get_db)) -> dict:
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=404, detail="user not found")
    if len(payload.new_password) < 8:
        raise HTTPException(status_code=400, detail="password must be at least 8 characters")

    user.password_hash = hash_password(payload.new_password)
    db.commit()
    return {"updated": True}


@router.delete("/admin/users/{user_id}")
def delete_user(user_id: int, db: Session = Depends(get_db), current: User = Depends(get_current_user)) -> dict:
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=404, detail="user not found")
    if user.id == current.id:
        raise HTTPException(status_code=400, detail="cannot delete your own account")
    if user.role == "admin":
        remaining_admins = db.query(User).filter(User.role == "admin", User.id != user.id).count()
        if remaining_admins == 0:
            raise HTTPException(status_code=400, detail="cannot delete the last remaining admin")

    db.query(InviteCode).filter(InviteCode.used_by_id == user.id).update({"used_by_id": None})
    db.query(LoginEvent).filter(LoginEvent.user_id == user.id).delete()
    db.delete(user)
    db.commit()
    return {"deleted": True}


@router.get("/admin/invite-codes", response_model=list[InviteCodeOut])
def list_invite_codes(db: Session = Depends(get_db)) -> list[InviteCodeOut]:
    invites = db.query(InviteCode).order_by(InviteCode.created_at.desc()).all()
    usernames = {u.id: u.username for u in db.query(User).all()}
    return [_invite_out(i, usernames) for i in invites]


@router.post("/admin/invite-codes", response_model=InviteCodeOut)
def create_invite_code(payload: CreateInviteCodeRequest, db: Session = Depends(get_db), current: User = Depends(get_current_user)) -> InviteCodeOut:
    code = secrets.token_urlsafe(6).upper().replace("_", "").replace("-", "")[:8]
    invite = InviteCode(code=code, label=payload.label, created_by_id=current.id)
    db.add(invite)
    db.commit()
    usernames = {u.id: u.username for u in db.query(User).all()}
    return _invite_out(invite, usernames)


@router.delete("/admin/invite-codes/{invite_id}")
def revoke_invite_code(invite_id: int, db: Session = Depends(get_db)) -> dict:
    invite = db.query(InviteCode).filter(InviteCode.id == invite_id).first()
    if invite is None:
        raise HTTPException(status_code=404, detail="invite code not found")
    if invite.used_by_id is not None:
        raise HTTPException(status_code=400, detail="cannot revoke a code that has already been used")
    invite.revoked = True
    db.commit()
    return {"revoked": True}


@router.get("/admin/activity", response_model=list[LoginEventOut])
def list_activity(db: Session = Depends(get_db)) -> list[LoginEventOut]:
    rows = db.query(LoginEvent).order_by(LoginEvent.created_at.desc()).limit(100).all()
    usernames = {u.id: u.username for u in db.query(User).all()}
    return [
        LoginEventOut(
            id=r.id, username=usernames.get(r.user_id, "?"), event_type=r.event_type,
            created_at=r.created_at, ip_address=r.ip_address,
        )
        for r in rows
    ]
