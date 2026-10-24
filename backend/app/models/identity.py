"""Usuários, sessões e tokens de e-mail."""
import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, LargeBinary, String, func
from sqlalchemy.dialects.postgresql import CITEXT, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, created_at_col

ROLES = ("USER", "ADMIN")
STATUSES = ("pending_approval", "active", "suspended", "rejected")
TOKEN_PURPOSES = ("verify_email", "reset_password")


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(f"role IN {ROLES}", name="role_valid"),
        CheckConstraint(f"status IN {STATUSES}", name="status_valid"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    email: Mapped[str] = mapped_column(CITEXT, unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(80), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(10), nullable=False, server_default="USER")
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="pending_approval"
    )
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    sessions: Mapped[list["UserSession"]] = relationship(
        back_populates="user", passive_deletes=True
    )


class UserSession(Base):
    """Sessão de login. O cookie guarda um token aleatório; o banco guarda só o hash."""

    __tablename__ = "user_sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token_hash: Mapped[bytes] = mapped_column(LargeBinary(32), unique=True, nullable=False)
    created_at: Mapped[datetime] = created_at_col()
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    user_agent: Mapped[str | None] = mapped_column(String(200))
    ip: Mapped[str | None] = mapped_column(String(64))

    user: Mapped[User] = relationship(back_populates="sessions")


class AuthToken(Base):
    """Tokens de uso único enviados por e-mail (verificação e redefinição de senha)."""

    __tablename__ = "auth_tokens"
    __table_args__ = (CheckConstraint(f"purpose IN {TOKEN_PURPOSES}", name="purpose_valid"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    purpose: Mapped[str] = mapped_column(String(20), nullable=False)
    token_hash: Mapped[bytes] = mapped_column(LargeBinary(32), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = created_at_col()
