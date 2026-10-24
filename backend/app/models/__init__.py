"""Modelos do banco. Importar este pacote registra todas as tabelas no metadata."""
from app.models.base import Base
from app.models.identity import AuthToken, User, UserSession
from app.models.admin import AppSetting, AuditLog, Invite
from app.models.preferences import UserPreferences

__all__ = [
    "Base",
    "User",
    "UserSession",
    "AuthToken",
    "Invite",
    "AppSetting",
    "AuditLog",
    "UserPreferences",
]
