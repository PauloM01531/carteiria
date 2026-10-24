"""Esquemas de categorias e lançamentos. Valores monetários trafegam como texto decimal ("1234.56")."""
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, PlainSerializer, field_validator

from app.schemas import In

Kind = Literal["income", "expense"]
PaymentMethod = Literal["pix", "dinheiro", "debito", "credito", "boleto", "transferencia", "outro"]
TxStatus = Literal["settled", "pending"]

# Decimal serializado como string para o JSON não virar float no navegador.
Money = Annotated[Decimal, PlainSerializer(lambda v: f"{v:.2f}", return_type=str)]
MoneyIn = Annotated[Decimal, Field(gt=0, max_digits=12, decimal_places=2)]

MIN_DATE = date(2000, 1, 1)
MAX_DATE = date(2100, 12, 31)


def _clean_text(v: str | None, field: str, max_len: int, required: bool) -> str | None:
    if v is None:
        return None
    v = " ".join(v.split())
    if any(ord(c) < 32 for c in v):
        raise ValueError(f"{field} contém caracteres inválidos.")
    if required and not v:
        raise ValueError(f"Informe {field}.")
    if len(v) > max_len:
        raise ValueError(f"{field} deve ter no máximo {max_len} caracteres.")
    return v or None


def _check_date(v: date) -> date:
    if not (MIN_DATE <= v <= MAX_DATE):
        raise ValueError("Data fora do intervalo permitido.")
    return v


class CategoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    kind: str
    active: bool
    is_system: bool


class TransactionCreate(In):
    kind: Kind
    description: str
    amount: MoneyIn
    occurred_on: date
    category_id: uuid.UUID
    payment_method: PaymentMethod
    status: TxStatus = "settled"
    notes: str | None = None

    @field_validator("description")
    @classmethod
    def _desc(cls, v: str) -> str:
        return _clean_text(v, "a descrição", 200, True)  # type: ignore[return-value]

    @field_validator("notes")
    @classmethod
    def _notes(cls, v: str | None) -> str | None:
        return _clean_text(v, "as observações", 500, False)

    _date = field_validator("occurred_on")(_check_date)


class TransactionUpdate(In):
    """Todos os campos opcionais. O dono do lançamento nunca pode ser alterado."""

    kind: Kind | None = None
    description: str | None = None
    amount: MoneyIn | None = None
    occurred_on: date | None = None
    category_id: uuid.UUID | None = None
    payment_method: PaymentMethod | None = None
    status: TxStatus | None = None
    notes: str | None = None

    @field_validator("description")
    @classmethod
    def _desc(cls, v: str | None) -> str | None:
        return _clean_text(v, "a descrição", 200, True)

    @field_validator("notes")
    @classmethod
    def _notes(cls, v: str | None) -> str | None:
        return _clean_text(v, "as observações", 500, False)

    @field_validator("occurred_on")
    @classmethod
    def _date(cls, v: date | None) -> date | None:
        return _check_date(v) if v else v


class TransactionOut(BaseModel):
    id: uuid.UUID
    kind: str
    description: str
    amount: Money
    occurred_on: date
    category_id: uuid.UUID
    category_name: str
    payment_method: str
    status: str
    notes: str | None
    created_at: datetime
    updated_at: datetime


class Totals(BaseModel):
    income: Money
    expense: Money
    balance: Money
    count: int


class TransactionPage(BaseModel):
    items: list[TransactionOut]
    total: int
    page: int
    page_size: int
    totals: Totals
