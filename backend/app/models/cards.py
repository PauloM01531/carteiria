"""Cartões, faturas, compras parceladas, pagamentos de fatura e contas recorrentes."""
import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, CheckConstraint, Date, ForeignKey, Index, Numeric, String, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, created_at_col
from app.models.finance import Category

FREQUENCIES = ("monthly", "bimonthly", "quarterly", "semiannual", "yearly")
FREQ_MONTHS = {"monthly": 1, "bimonthly": 2, "quarterly": 3, "semiannual": 6, "yearly": 12}


def _pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())


def _owner() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)


class Card(Base):
    __tablename__ = "cards"
    __table_args__ = (
        CheckConstraint("closing_day BETWEEN 1 AND 31", name="closing_day_valid"),
        CheckConstraint("due_day BETWEEN 1 AND 31", name="due_day_valid"),
        CheckConstraint("credit_limit IS NULL OR credit_limit > 0", name="limit_positive"),
    )

    id: Mapped[uuid.UUID] = _pk()
    user_id: Mapped[uuid.UUID] = _owner()
    nickname: Mapped[str] = mapped_column(String(60), nullable=False)
    institution: Mapped[str | None] = mapped_column(String(60))
    closing_day: Mapped[int] = mapped_column(nullable=False)
    due_day: Mapped[int] = mapped_column(nullable=False)
    credit_limit: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    created_at: Mapped[datetime] = created_at_col()


class CardStatement(Base):
    """Fatura: uma por cartão e competência (mês de referência). O total é a soma das parcelas."""

    __tablename__ = "card_statements"
    __table_args__ = (
        Index("uq_card_statements_card_month", "card_id", "reference_month", unique=True),
        CheckConstraint("extract(day from reference_month) = 1", name="reference_first_day"),
    )

    id: Mapped[uuid.UUID] = _pk()
    user_id: Mapped[uuid.UUID] = _owner()
    card_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("cards.id", ondelete="CASCADE"), nullable=False)
    reference_month: Mapped[date] = mapped_column(Date, nullable=False)
    closing_date: Mapped[date] = mapped_column(Date, nullable=False)
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    created_at: Mapped[datetime] = created_at_col()

    card: Mapped[Card] = relationship(lazy="joined")


class CardPurchase(Base):
    __tablename__ = "card_purchases"
    __table_args__ = (
        CheckConstraint("total_amount > 0", name="amount_positive"),
        CheckConstraint("installments_count BETWEEN 1 AND 72", name="installments_valid"),
        CheckConstraint("extract(day from first_statement_month) = 1", name="first_month_first_day"),
    )

    id: Mapped[uuid.UUID] = _pk()
    user_id: Mapped[uuid.UUID] = _owner()
    card_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("cards.id"), nullable=False, index=True)
    description: Mapped[str] = mapped_column(String(200), nullable=False)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    purchase_date: Mapped[date] = mapped_column(Date, nullable=False)
    category_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("categories.id"), nullable=False)
    installments_count: Mapped[int] = mapped_column(nullable=False)
    first_statement_month: Mapped[date] = mapped_column(Date, nullable=False)
    notes: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = created_at_col()

    category: Mapped[Category] = relationship(lazy="joined")
    card: Mapped[Card] = relationship(lazy="joined")
    installments: Mapped[list["Installment"]] = relationship(
        back_populates="purchase", order_by="Installment.number", cascade="all, delete-orphan", passive_deletes=True
    )


class Installment(Base):
    __tablename__ = "installments"
    __table_args__ = (
        Index("uq_installments_purchase_number", "purchase_id", "number", unique=True),
        CheckConstraint("amount > 0", name="amount_positive"),
        CheckConstraint("number >= 1", name="number_valid"),
    )

    id: Mapped[uuid.UUID] = _pk()
    user_id: Mapped[uuid.UUID] = _owner()
    purchase_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("card_purchases.id", ondelete="CASCADE"), nullable=False)
    statement_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("card_statements.id"), nullable=False, index=True)
    number: Mapped[int] = mapped_column(nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)

    purchase: Mapped[CardPurchase] = relationship(back_populates="installments")


class StatementPayment(Base):
    __tablename__ = "statement_payments"
    __table_args__ = (CheckConstraint("amount > 0", name="amount_positive"),)

    id: Mapped[uuid.UUID] = _pk()
    user_id: Mapped[uuid.UUID] = _owner()
    statement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("card_statements.id", ondelete="CASCADE"), nullable=False, index=True
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    paid_on: Mapped[date] = mapped_column(Date, nullable=False)
    notes: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = created_at_col()


class RecurringBill(Base):
    __tablename__ = "recurring_bills"
    __table_args__ = (
        CheckConstraint("amount_type IN ('fixed', 'variable')", name="amount_type_valid"),
        CheckConstraint(f"frequency IN {FREQUENCIES}", name="frequency_valid"),
        CheckConstraint("due_day BETWEEN 1 AND 31", name="due_day_valid"),
        CheckConstraint("expected_amount IS NULL OR expected_amount > 0", name="amount_positive"),
        CheckConstraint("amount_type = 'variable' OR expected_amount IS NOT NULL", name="fixed_has_amount"),
        CheckConstraint("end_date IS NULL OR end_date >= start_date", name="end_after_start"),
    )

    id: Mapped[uuid.UUID] = _pk()
    user_id: Mapped[uuid.UUID] = _owner()
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    amount_type: Mapped[str] = mapped_column(String(10), nullable=False)
    expected_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    category_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("categories.id"), nullable=False)
    frequency: Mapped[str] = mapped_column(String(12), nullable=False, server_default="monthly")
    due_day: Mapped[int] = mapped_column(nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date | None] = mapped_column(Date)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    notes: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = created_at_col()

    category: Mapped[Category] = relationship(lazy="joined")


class BillOccurrence(Base):
    """Uma ocorrência por conta e vencimento (índice único evita duplicidade).
    Ocorrência pendente é PREVISÃO; só vira despesa quando paga (cria um lançamento)."""

    __tablename__ = "bill_occurrences"
    __table_args__ = (
        Index("uq_bill_occurrences_bill_due", "bill_id", "due_date", unique=True),
        CheckConstraint("status IN ('pending', 'paid')", name="status_valid"),
        CheckConstraint("amount IS NULL OR amount > 0", name="amount_positive"),
        CheckConstraint("status = 'pending' OR paid_on IS NOT NULL", name="paid_has_date"),
    )

    id: Mapped[uuid.UUID] = _pk()
    user_id: Mapped[uuid.UUID] = _owner()
    bill_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("recurring_bills.id", ondelete="CASCADE"), nullable=False
    )
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    status: Mapped[str] = mapped_column(String(10), nullable=False, server_default="pending")
    paid_on: Mapped[date | None] = mapped_column(Date)
    transaction_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("transactions.id", ondelete="SET NULL")
    )

    bill: Mapped[RecurringBill] = relationship(lazy="joined")
