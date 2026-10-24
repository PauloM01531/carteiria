"""Preferências pessoais — primeira tabela privada protegida por RLS."""
import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

THEMES = ("system", "light", "dark")


class UserPreferences(Base):
    __tablename__ = "user_preferences"
    __table_args__ = (CheckConstraint(f"theme IN {THEMES}", name="theme_valid"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    theme: Mapped[str] = mapped_column(String(10), nullable=False, server_default="system")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
