"""Registro de eventos administrativos e de segurança (sem senhas, tokens ou dados financeiros)."""
import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.models import AuditLog


def record(
    db: Session,
    action: str,
    result: str,
    *,
    actor_id: uuid.UUID | None = None,
    actor_email: str | None = None,
    target_user_id: uuid.UUID | None = None,
    details: dict[str, Any] | None = None,
    ip: str | None = None,
) -> None:
    db.add(
        AuditLog(
            action=action,
            result=result,
            actor_id=actor_id,
            actor_email=actor_email,
            target_user_id=target_user_id,
            details=details or {},
            ip=ip,
        )
    )
