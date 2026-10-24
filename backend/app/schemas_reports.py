"""Esquemas de relatórios, painel, orçamentos e metas. Valores sempre como texto decimal."""
import uuid
from datetime import date
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, Field, PlainSerializer, field_validator

from app.schemas import In
from app.schemas_finance import Money, MoneyIn, _check_date, _clean_text

Pct = Annotated[Decimal, PlainSerializer(lambda v: f"{v:.1f}", return_type=str)]
Basis = Literal["competencia", "lancamento", "caixa"]


class LargestExpense(BaseModel):
    description: str
    amount: Money
    day: date
    category_name: str
    source: str


class CategoryShare(BaseModel):
    category_id: uuid.UUID | None
    category_name: str
    amount: Money
    share: Pct


class SummaryOut(BaseModel):
    start: date
    end: date
    basis: str
    income: Money
    expense: Money
    balance: Money
    savings_rate: Pct | None
    largest_expense: LargestExpense | None
    top_category: CategoryShare | None
    count: int


class MonthPoint(BaseModel):
    month: date
    income: Money
    expense: Money
    balance: Money
    cumulative: Money


class Diff(BaseModel):
    previous: Money
    current: Money
    diff: Money
    pct: Pct | None


class CategoryDiff(BaseModel):
    category_name: str
    previous: Money
    current: Money
    diff: Money
    pct: Pct | None


class CompareOut(BaseModel):
    month_a: date
    month_b: date
    basis: str
    income: Diff
    expense: Diff
    balance: Diff
    categories: list[CategoryDiff]


class OpenStatement(BaseModel):
    id: uuid.UUID
    card_nickname: str
    reference_month: date
    due_date: date
    remaining: Money


class MonthAmount(BaseModel):
    month: date
    amount: Money


class UpcomingBill(BaseModel):
    id: uuid.UUID
    name: str
    due_date: date
    amount: Money | None
    overdue: bool


class CommitmentsOut(BaseModel):
    reference_date: date
    open_statements: list[OpenStatement]
    open_statements_total: Money
    future_installments_total: Money
    future_installments_by_month: list[MonthAmount]
    upcoming_bills: list[UpcomingBill]
    upcoming_bills_total: Money
    pending_expenses_total: Money
    total: Money


class RecentTx(BaseModel):
    id: uuid.UUID
    kind: str
    description: str
    amount: Money
    occurred_on: date
    category_name: str
    status: str


# ---------------------------------------------------------------- orçamentos

class PrevMonth(BaseModel):
    month: date
    spent: Money


class BudgetOut(BaseModel):
    id: uuid.UUID
    category_id: uuid.UUID
    category_name: str
    month: date
    limit_amount: Money
    spent: Money
    remaining: Money
    percent: Pct
    status: Literal["ok", "warning", "limit", "over"]
    previous_months: list[PrevMonth]
    previous_average: Money


class BudgetCreate(In):
    category_id: uuid.UUID
    month: date
    limit_amount: MoneyIn

    _m = field_validator("month")(_check_date)


class BudgetUpdate(In):
    limit_amount: MoneyIn


class BudgetCopy(In):
    source_month: date
    target_month: date


class DashboardOut(BaseModel):
    month: date
    summary: SummaryOut
    previous_summary: SummaryOut
    expense_change_pct: Pct | None
    cash_balance: Money
    balance_after_commitments: Money
    month_statements_total: Money
    commitments: CommitmentsOut
    monthly: list[MonthPoint]
    categories: list[CategoryShare]
    budgets: list[BudgetOut]
    recent: list[RecentTx]


# ---------------------------------------------------------------- metas

class GoalCreate(In):
    name: str
    target_amount: MoneyIn
    deadline: date | None = None
    notes: str | None = None

    _n = field_validator("name")(lambda v: _clean_text(v, "o nome", 100, True))
    _no = field_validator("notes")(lambda v: _clean_text(v, "as observações", 500, False))
    _d = field_validator("deadline")(lambda v: _check_date(v) if v else v)


class GoalUpdate(In):
    name: str | None = None
    target_amount: MoneyIn | None = None
    deadline: date | None = None
    notes: str | None = None

    _n = field_validator("name")(lambda v: _clean_text(v, "o nome", 100, True))
    _no = field_validator("notes")(lambda v: _clean_text(v, "as observações", 500, False))
    _d = field_validator("deadline")(lambda v: _check_date(v) if v else v)


class ContributionIn(In):
    amount: Annotated[Decimal, Field(max_digits=12, decimal_places=2)]
    contributed_on: date
    notes: str | None = None

    _d = field_validator("contributed_on")(_check_date)
    _no = field_validator("notes")(lambda v: _clean_text(v, "as observações", 200, False))

    @field_validator("amount")
    @classmethod
    def _nz(cls, v: Decimal) -> Decimal:
        if v == 0:
            raise ValueError("O valor não pode ser zero.")
        return v


class ContributionOut(BaseModel):
    id: uuid.UUID
    amount: Money
    contributed_on: date
    notes: str | None


class GoalOut(BaseModel):
    id: uuid.UUID
    name: str
    target_amount: Money
    deadline: date | None
    notes: str | None
    saved: Money
    remaining: Money
    percent: Pct
    status: Literal["achieved", "late", "in_progress"]
    months_left: int | None
    monthly_needed: Money | None
    contributions: list[ContributionOut]
