"""Tokens de uso único enviados por e-mail."""
import uuid
from datetime import timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models import AuthToken
from app.security.tokens import hash_token, new_token
from app.services.sessions import utcnow


def issue(db: Session, user_id: uuid.UUID, purpose: str, ttl: timedelta) -> str:
    # Invalida tokens anteriores do mesmo tipo: só o mais recente vale.
    db.execute(
        update(AuthToken)
        .where(
            AuthToken.user_id == user_id,
            AuthToken.purpose == purpose,
            AuthToken.used_at.is_(None),
        )
        .values(used_at=utcnow())
    )
    token = new_token()
    db.add(
        AuthToken(
            user_id=user_id, purpose=purpose, token_hash=hash_token(token), expires_at=utcnow() + ttl
        )
    )
    db.flush()
    return token


def consume(db: Session, token: str, purpose: str) -> AuthToken | None:
    """Marca o token como usado e o devolve, ou None se inválido/expirado/já usado."""
    row = db.scalar(
        select(AuthToken)
        .where(AuthToken.token_hash == hash_token(token), AuthToken.purpose == purpose)
        .with_for_update()
    )
    if row is None or row.used_at is not None or row.expires_at <= utcnow():
        return None
    row.used_at = utcnow()
    return row
