"""Criação, validação e revogação de sessões de login."""
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session, joinedload

from app.config import get_settings
from app.models import User, UserSession
from app.security.tokens import hash_token, new_token


def utcnow() -> datetime:
    return datetime.now(UTC)


def create_session(db: Session, user: User, user_agent: str | None, ip: str | None) -> str:
    """Cria a sessão e devolve o token em claro (vai somente para o cookie HttpOnly)."""
    token = new_token()
    db.add(
        UserSession(
            user_id=user.id,
            token_hash=hash_token(token),
            expires_at=utcnow() + timedelta(hours=get_settings().session_absolute_hours),
            user_agent=(user_agent or "")[:200] or None,
            ip=ip,
        )
    )
    db.flush()
    return token


def find_valid_session(db: Session, token: str) -> UserSession | None:
    s = get_settings()
    now = utcnow()
    sess = db.scalar(
        select(UserSession)
        .options(joinedload(UserSession.user))
        .where(UserSession.token_hash == hash_token(token))
    )
    if sess is None or sess.revoked_at is not None:
        return None
    if sess.expires_at <= now:
        return None
    if sess.last_seen_at <= now - timedelta(minutes=s.session_idle_minutes):
        return None
    return sess


def touch(db: Session, sess: UserSession) -> None:
    if utcnow() - sess.last_seen_at > timedelta(minutes=1):
        sess.last_seen_at = utcnow()


def revoke_token(db: Session, token: str) -> None:
    db.execute(
        update(UserSession)
        .where(UserSession.token_hash == hash_token(token), UserSession.revoked_at.is_(None))
        .values(revoked_at=utcnow())
    )


def revoke_all(db: Session, user_id: uuid.UUID, except_id: uuid.UUID | None = None) -> None:
    stmt = update(UserSession).where(
        UserSession.user_id == user_id, UserSession.revoked_at.is_(None)
    )
    if except_id is not None:
        stmt = stmt.where(UserSession.id != except_id)
    db.execute(stmt.values(revoked_at=utcnow()))
