"""Categorias e lançamentos (receitas e despesas)."""
import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index, Numeric, String, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, created_at_col

KINDS = ("income", "expense")
PAYMENT_METHODS = ("pix", "dinheiro", "debito", "credito", "boleto", "transferencia", "outro")
TX_STATUSES = ("settled", "pending")


class Category(Base):
    """user_id NULL = categoria padrão do sistema (visível a todos, só leitura).
    Categorias não são apagadas, apenas desativadas, para preservar o histórico."""

    __tablename__ = "categories"
    __table_args__ = (
        CheckConstraint(f"kind IN {KINDS}", name="kind_valid"),
        Index("uq_categories_system_name", "kind", text("lower(name)"), unique=True,
              postgresql_where=text("user_id IS NULL")),
        Index("uq_categories_user_name", "user_id", "kind", text("lower(name)"), unique=True,
              postgresql_where=text("user_id IS NOT NULL")),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(60), nullable=False)
    kind: Mapped[str] = mapped_column(String(10), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    created_at: Mapped[datetime] = created_at_col()


class Transaction(Base):
    __tablename__ = "transactions"
    __table_args__ = (
        CheckConstraint(f"kind IN {KINDS}", name="kind_valid"),
        CheckConstraint("amount > 0", name="amount_positive"),
        CheckConstraint(f"payment_method IN {PAYMENT_METHODS}", name="payment_method_valid"),
        CheckConstraint(f"status IN {TX_STATUSES}", name="status_valid"),
        Index("ix_transactions_user_date", "user_id", "occurred_on"),
        Index("ix_transactions_user_category", "user_id", "category_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(10), nullable=False)
    description: Mapped[str] = mapped_column(String(200), nullable=False)
    # Valores monetários sempre NUMERIC/Decimal, nunca float.
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    occurred_on: Mapped[date] = mapped_column(Date, nullable=False)
    category_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("categories.id"), nullable=False
    )
    payment_method: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(10), nullable=False, server_default="settled")
    notes: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    category: Mapped[Category] = relationship(lazy="joined")
