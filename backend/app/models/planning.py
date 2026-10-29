"""Orçamentos mensais por categoria e metas financeiras."""
import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, Date, ForeignKey, Index, Numeric, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, created_at_col
from app.models.finance import Category


class Budget(Base):
    __tablename__ = "budgets"
    __table_args__ = (
        Index("uq_budgets_user_category_month", "user_id", "category_id", "month", unique=True),
        CheckConstraint("limit_amount > 0", name="limit_positive"),
        CheckConstraint("extract(day from month) = 1", name="month_first_day"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    category_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("categories.id"), nullable=False)
    month: Mapped[date] = mapped_column(Date, nullable=False)
    limit_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    created_at: Mapped[datetime] = created_at_col()

    category: Mapped[Category] = relationship(lazy="joined")


class Goal(Base):
    __tablename__ = "goals"
    __table_args__ = (CheckConstraint("target_amount > 0", name="target_positive"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    target_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    deadline: Mapped[date | None] = mapped_column(Date)
    notes: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = created_at_col()

    contributions: Mapped[list["GoalContribution"]] = relationship(
        back_populates="goal", order_by="GoalContribution.contributed_on", cascade="all, delete-orphan", passive_deletes=True
    )


class GoalContribution(Base):
    """Aporte (valor positivo) ou retirada (valor negativo) em uma meta."""

    __tablename__ = "goal_contributions"
    __table_args__ = (CheckConstraint("amount <> 0", name="amount_nonzero"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    goal_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("goals.id", ondelete="CASCADE"), nullable=False, index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    contributed_on: Mapped[date] = mapped_column(Date, nullable=False)
    notes: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = created_at_col()

    goal: Mapped[Goal] = relationship(back_populates="contributions")


class PlannedPurchase(Base):
    """Compra futura em avaliação (simulação). NÃO é despesa nem compra de cartão:
    não entra em relatórios, faturas ou painel até ser registrada de fato."""

    __tablename__ = "planned_purchases"
    __table_args__ = (
        CheckConstraint("total_amount > 0", name="amount_positive"),
        CheckConstraint("installments_count BETWEEN 1 AND 72", name="installments_valid"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    installments_count: Mapped[int] = mapped_column(nullable=False)
    first_installment_date: Mapped[date] = mapped_column(Date, nullable=False)
    category_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("categories.id"), nullable=False)
    notes: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = created_at_col()

    category: Mapped[Category] = relationship(lazy="joined")
