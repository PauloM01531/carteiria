"""Esquemas de entrada/saída. Entradas rejeitam campos desconhecidos (extra="forbid"),
então enviar `user_id`, `role` ou `status` no corpo resulta em erro 422."""
import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class In(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


def _clean_name(v: str) -> str:
    v = " ".join(v.split())
    if any(ord(c) < 32 for c in v) or "<" in v or ">" in v:
        raise ValueError("Nome contém caracteres não permitidos.")
    if len(v) < 2:
        raise ValueError("Informe um nome com pelo menos 2 caracteres.")
    return v


# ---------- Autenticação ----------
class RegisterIn(In):
    display_name: str = Field(max_length=80)
    email: EmailStr = Field(max_length=254)
    password: str = Field(max_length=128)
    invite_token: str | None = Field(default=None, max_length=100)

    _name = field_validator("display_name")(_clean_name)


class LoginIn(In):
    email: EmailStr = Field(max_length=254)
    password: str = Field(max_length=128)


class EmailIn(In):
    email: EmailStr = Field(max_length=254)


class TokenIn(In):
    token: str = Field(min_length=10, max_length=100)


class ResetPasswordIn(In):
    token: str = Field(min_length=10, max_length=100)
    password: str = Field(max_length=128)


class ChangePasswordIn(In):
    current_password: str = Field(max_length=128)
    new_password: str = Field(max_length=128)


class MessageOut(BaseModel):
    message: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    display_name: str
    role: str
    status: str
    created_at: datetime
    mfa_enabled: bool = False


class SessionOut(BaseModel):
    user: UserOut
    csrf_token: str


class MfaChallengeOut(BaseModel):
    mfa_required: bool = True
    challenge: str


class MfaLoginIn(In):
    challenge: str = Field(min_length=10, max_length=100)
    code: str = Field(min_length=6, max_length=8)


class ReauthIn(In):
    password: str = Field(max_length=128)
    code: str | None = Field(default=None, max_length=8)


class MfaSetupIn(In):
    password: str = Field(max_length=128)


class MfaSetupOut(BaseModel):
    secret: str
    otpauth_uri: str


class MfaCodeIn(In):
    code: str = Field(min_length=6, max_length=8)


class MfaDisableIn(In):
    password: str = Field(max_length=128)
    code: str = Field(min_length=6, max_length=8)


class MfaStatusOut(BaseModel):
    enabled: bool
    required: bool


# ---------- Perfil ----------
class ProfileUpdateIn(In):
    display_name: str = Field(max_length=80)

    _name = field_validator("display_name")(_clean_name)


class PreferencesIn(In):
    theme: Literal["system", "light", "dark"]


class PreferencesOut(BaseModel):
    theme: str


class DeviceSessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    created_at: datetime
    last_seen_at: datetime
    user_agent: str | None
    ip: str | None
    current: bool = False


class DeleteAccountIn(In):
    password: str = Field(max_length=128)
    confirmation: Literal["EXCLUIR"]


# ---------- Administração ----------
class AdminUserOut(BaseModel):
    """Somente dados necessários para administrar a plataforma (nada financeiro)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    display_name: str
    role: str
    status: str
    email_verified: bool
    created_at: datetime
    last_login_at: datetime | None


class RegistrationModeIn(In):
    mode: Literal["closed", "approval", "invite"]


class RegistrationModeOut(BaseModel):
    mode: str


class InviteIn(In):
    email: EmailStr = Field(max_length=254)


class InviteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    expires_at: datetime
    used_at: datetime | None
    revoked_at: datetime | None
    created_at: datetime


class InviteCreatedOut(BaseModel):
    invite: InviteOut
    link: str


class AuditLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    actor_id: uuid.UUID | None
    actor_email: str | None
    action: str
    target_user_id: uuid.UUID | None
    result: str
    details: dict
    created_at: datetime


class AdminStatsOut(BaseModel):
    total_users: int
    by_status: dict[str, int]
    pending_invites: int
