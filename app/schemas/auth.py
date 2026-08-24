from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class RegisterRequest(BaseModel):
    code: str
    username: str
    password: str


class LoginRequest(BaseModel):
    username: str
    password: str


class UserOut(BaseModel):
    id: int
    username: str
    role: str
    is_active: bool
    created_at: datetime
    last_login_at: datetime | None = None
    last_active_at: datetime | None = None
    login_count: int
    language: str
    language_confirmed: bool


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class SetLanguageRequest(BaseModel):
    language: str


class InviteCodeOut(BaseModel):
    id: int
    code: str
    label: str
    created_at: datetime
    created_by: str
    used_by: str | None = None
    used_at: datetime | None = None
    revoked: bool


class CreateInviteCodeRequest(BaseModel):
    label: str = ""


class UpdateUserRequest(BaseModel):
    role: str | None = None
    is_active: bool | None = None


class UpdatePasswordRequest(BaseModel):
    new_password: str


class LoginEventOut(BaseModel):
    id: int
    username: str
    event_type: str
    created_at: datetime
    ip_address: str | None = None
