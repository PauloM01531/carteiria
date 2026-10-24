"""Esquemas de categorias personalizadas, cartões, compras, faturas e contas recorrentes."""
import uuid
from datetime import date
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.schemas import In
from app.schemas_finance import Kind, Money, MoneyIn, PaymentMethod, _check_date, _clean_text

Day = Annotated[int, Field(ge=1, le=31)]
Frequency = Literal["monthly", "bimonthly", "quarterly", "semiannual", "yearly"]


def _month(v: date | None) -> date | None:
    """Competência sempre no 1º dia do mês."""
    if v is None:
        return v
    _check_date(v)
    return v.replace(day=1)


# ---------------------------------------------------------------- categorias

class CategoryCreate(In):
    name: str
    kind: Kind

    @field_validator("name")
    @classmethod
    def _name(cls, v: str) -> str:
        return _clean_text(v, "o nome", 60, True)  # type: ignore[return-value]


class CategoryUpdate(In):
    name: str | None = None
    active: bool | None = None

    @field_validator("name")
    @classmethod
    def _name(cls, v: str | None) -> str | None:
        return _clean_text(v, "o nome", 60, True)


# ---------------------------------------------------------------- cartões

class CardCreate(In):
    nickname: str
    institution: str | None = None
    closing_day: Day
    due_day: Day
    credit_limit: MoneyIn | None = None

    @field_validator("nickname")
    @classmethod
    def _nick(cls, v: str) -> str:
        return _clean_text(v, "o apelido", 60, True)  # type: ignore[return-value]

    @field_validator("institution")
    @classmethod
    def _inst(cls, v: str | None) -> str | None:
        return _clean_text(v, "a instituição", 60, False)


class CardUpdate(In):
    nickname: str | None = None
    institution: str | None = None
    closing_day: Day | None = None
    due_day: Day | None = None
    credit_limit: MoneyIn | None = None
    active: bool | None = None

    _nick = field_validator("nickname")(lambda v: _clean_text(v, "o apelido", 60, True))
    _inst = field_validator("institution")(lambda v: _clean_text(v, "a instituição", 60, False))


class CardOut(BaseModel):
    id: uuid.UUID
    nickname: str
    institution: str | None
    closing_day: int
    due_day: int
    credit_limit: Money | None
    active: bool
    used_amount: Money
    available_limit: Money | None


class StatementSuggestion(BaseModel):
    reference_month: date
    closing_date: date
    due_date: date


# ---------------------------------------------------------------- compras

class PurchaseCreate(In):
    card_id: uuid.UUID
    description: str
    total_amount: MoneyIn
    purchase_date: date
    category_id: uuid.UUID
    installments_count: Annotated[int, Field(ge=1, le=72)] = 1
    first_statement_month: date | None = None   # opcional: o servidor sugere pelo fechamento
    notes: str | None = None

    _desc = field_validator("description")(lambda v: _clean_text(v, "a descrição", 200, True))
    _notes = field_validator("notes")(lambda v: _clean_text(v, "as observações", 500, False))
    _date = field_validator("purchase_date")(_check_date)
    _month = field_validator("first_statement_month")(_month)


class PurchaseUpdate(In):
    card_id: uuid.UUID | None = None
    description: str | None = None
    total_amount: MoneyIn | None = None
    purchase_date: date | None = None
    category_id: uuid.UUID | None = None
    installments_count: Annotated[int, Field(ge=1, le=72)] | None = None
    first_statement_month: date | None = None
    notes: str | None = None

    _desc = field_validator("description")(lambda v: _clean_text(v, "a descrição", 200, True))
    _notes = field_validator("notes")(lambda v: _clean_text(v, "as observações", 500, False))
    _date = field_validator("purchase_date")(lambda v: _check_date(v) if v else v)
    _month = field_validator("first_statement_month")(_month)


class InstallmentOut(BaseModel):
    id: uuid.UUID
    number: int
    amount: Money
    statement_id: uuid.UUID
    reference_month: date


class PurchaseOut(BaseModel):
    id: uuid.UUID
    card_id: uuid.UUID
    card_nickname: str
    description: str
    total_amount: Money
    purchase_date: date
    category_id: uuid.UUID
    category_name: str
    installments_count: int
    first_statement_month: date
    notes: str | None
    installments: list[InstallmentOut]


# ---------------------------------------------------------------- faturas

StatementStatus = Literal["open", "closed", "partial", "paid", "overdue", "empty"]


class StatementOut(BaseModel):
    id: uuid.UUID
    card_id: uuid.UUID
    card_nickname: str
    reference_month: date
    closing_date: date
    due_date: date
    total: Money
    paid: Money
    remaining: Money
    status: StatementStatus
    items_count: int


class StatementItemOut(BaseModel):
    installment_id: uuid.UUID
    purchase_id: uuid.UUID
    description: str
    purchase_date: date
    category_name: str
    number: int
    installments_count: int
    amount: Money


class PaymentOut(BaseModel):
    id: uuid.UUID
    amount: Money
    paid_on: date
    notes: str | None


class StatementDetailOut(StatementOut):
    items: list[StatementItemOut]
    payments: list[PaymentOut]


class PaymentCreate(In):
    amount: MoneyIn
    paid_on: date
    notes: str | None = None

    _date = field_validator("paid_on")(_check_date)
    _notes = field_validator("notes")(lambda v: _clean_text(v, "as observações", 200, False))


# ---------------------------------------------------------------- contas recorrentes

class BillCreate(In):
    name: str
    amount_type: Literal["fixed", "variable"] = "fixed"
    expected_amount: MoneyIn | None = None
    category_id: uuid.UUID
    frequency: Frequency = "monthly"
    due_day: Day
    start_date: date
    end_date: date | None = None
    notes: str | None = None

    _name = field_validator("name")(lambda v: _clean_text(v, "o nome", 100, True))
    _notes = field_validator("notes")(lambda v: _clean_text(v, "as observações", 500, False))
    _start = field_validator("start_date")(_check_date)
    _end = field_validator("end_date")(lambda v: _check_date(v) if v else v)

    @model_validator(mode="after")
    def _rules(self) -> "BillCreate":
        if self.amount_type == "fixed" and self.expected_amount is None:
            raise ValueError("Informe o valor da conta fixa.")
        if self.end_date and self.end_date < self.start_date:
            raise ValueError("A data final deve ser posterior à inicial.")
        return self


class BillUpdate(In):
    name: str | None = None
    amount_type: Literal["fixed", "variable"] | None = None
    expected_amount: MoneyIn | None = None
    category_id: uuid.UUID | None = None
    frequency: Frequency | None = None
    due_day: Day | None = None
    start_date: date | None = None
    end_date: date | None = None
    active: bool | None = None
    notes: str | None = None

    _name = field_validator("name")(lambda v: _clean_text(v, "o nome", 100, True))
    _notes = field_validator("notes")(lambda v: _clean_text(v, "as observações", 500, False))


class BillOut(BaseModel):
    id: uuid.UUID
    name: str
    amount_type: str
    expected_amount: Money | None
    category_id: uuid.UUID
    category_name: str
    frequency: str
    due_day: int
    start_date: date
    end_date: date | None
    active: bool
    notes: str | None


class OccurrenceOut(BaseModel):
    id: uuid.UUID
    bill_id: uuid.UUID
    bill_name: str
    category_name: str
    amount_type: str
    due_date: date
    amount: Money | None
    status: Literal["pending", "due_soon", "overdue", "paid"]
    paid_on: date | None
    transaction_id: uuid.UUID | None


class OccurrenceSummary(BaseModel):
    pending_total: Money
    paid_total: Money
    overdue_count: int


class OccurrenceList(BaseModel):
    items: list[OccurrenceOut]
    summary: OccurrenceSummary


class PayIn(In):
    paid_on: date
    amount: MoneyIn | None = None
    payment_method: PaymentMethod = "pix"

    _date = field_validator("paid_on")(_check_date)


class AmountIn(In):
    amount: MoneyIn


__all__ = ["Decimal"]
