"""Compras planejadas: simulação de compras futuras e análise de impacto no orçamento.
Endpoints documentados e reutilizáveis pela futura IA; o dono sempre vem da sessão."""
import uuid
from datetime import date
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, PlainSerializer, field_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import AuthContext, get_auth, get_auth_synced
from app.db import get_db
from app.models import PlannedPurchase
from app.schemas import In, MessageOut
from app.schemas_finance import Money, MoneyIn, _check_date, _clean_text
from app.security.rate_limit import enforce
from app.services import planned as svc

MAX_PLANNED = 30  # cada análise percorre até 72 meses: limita o custo por usuário

router = APIRouter(prefix="/planned-purchases", tags=["compras planejadas"])

Pct = Annotated[Decimal, PlainSerializer(lambda v: f"{v:.1f}", return_type=str)]
Status = Literal["fits", "attention", "over", "insufficient"]


class PlannedIn(In):
    name: str
    total_amount: MoneyIn
    installments_count: Annotated[int, Field(ge=1, le=72)]
    first_installment_date: date
    category_id: uuid.UUID
    notes: str | None = None

    _n = field_validator("name")(lambda v: _clean_text(v, "o nome", 200, True))
    _no = field_validator("notes")(lambda v: _clean_text(v, "as observações", 500, False))
    _d = field_validator("first_installment_date")(_check_date)


class PlannedUpdate(In):
    name: str | None = None
    total_amount: MoneyIn | None = None
    installments_count: Annotated[int, Field(ge=1, le=72)] | None = None
    first_installment_date: date | None = None
    category_id: uuid.UUID | None = None
    notes: str | None = None

    _n = field_validator("name")(lambda v: _clean_text(v, "o nome", 200, True))
    _no = field_validator("notes")(lambda v: _clean_text(v, "as observações", 500, False))
    _d = field_validator("first_installment_date")(lambda v: _check_date(v) if v else v)


class MonthOut(BaseModel):
    month: date
    number: int
    installment: Money
    income: Money | None
    income_source: str | None
    registered_expenses: Money
    card_installments: Money
    subscriptions_projected: Money
    bills_pending: Money
    variable_estimate: Money
    other_planned: Money
    committed: Money
    balance_before: Money | None
    balance_after: Money | None
    status: Status
    factors: list[str]
    notes: list[str]


class AnalysisOut(BaseModel):
    name: str
    total_amount: Money
    installments_count: int
    installment_amount: Money
    last_installment_amount: Money
    first_month: date
    last_month: date
    overall_status: Status
    headline: str
    status_counts: dict[str, int]
    worst_month: date | None
    worst_balance_after: Money | None
    average_balance_after: Money | None
    history_months: list[date]
    history_income_avg: Money | None
    history_variable_avg: Money | None
    confidence_notes: list[str]
    months: list[MonthOut]


class PlannedOut(BaseModel):
    id: uuid.UUID
    name: str
    total_amount: Money
    installments_count: int
    first_installment_date: date
    category_id: uuid.UUID
    category_name: str
    notes: str | None
    installment_amount: Money
    last_installment_amount: Money
    first_month: date
    last_month: date
    overall_status: Status
    headline: str


def _out(db: Session, uid: uuid.UUID, p: PlannedPurchase) -> PlannedOut:
    a = svc.analyze_saved(db, uid, p)
    return PlannedOut(
        id=p.id, name=p.name, total_amount=p.total_amount, installments_count=p.installments_count,
        first_installment_date=p.first_installment_date, category_id=p.category_id, category_name=p.category.name,
        notes=p.notes, installment_amount=a["installment_amount"], last_installment_amount=a["last_installment_amount"],
        first_month=a["first_month"], last_month=a["last_month"], overall_status=a["overall_status"], headline=a["headline"],
    )


@router.get("", response_model=list[PlannedOut], summary="Compras planejadas com a conclusão geral de cada uma")
def list_planned(ctx: AuthContext = Depends(get_auth_synced), db: Session = Depends(get_db)) -> list[PlannedOut]:
    rows = db.scalars(select(PlannedPurchase).where(PlannedPurchase.user_id == ctx.user.id)
                      .order_by(PlannedPurchase.first_installment_date, PlannedPurchase.created_at)).unique().all()
    return [_out(db, ctx.user.id, p) for p in rows]


@router.post("/simulate", response_model=AnalysisOut, summary="Analisa uma compra sem salvar")
def simulate(body: PlannedIn, ctx: AuthContext = Depends(get_auth_synced), db: Session = Depends(get_db)):
    enforce(f"planned-simulate:user:{ctx.user.id}", limit=60, window_seconds=3600)
    svc.check_inputs(db, ctx.user.id, body.total_amount, body.installments_count, body.category_id)
    return svc.analyze(db, ctx.user.id, body.name, body.total_amount, body.installments_count,
                       body.first_installment_date, body.category_id)


@router.post("", response_model=PlannedOut, status_code=201)
def create_planned(body: PlannedIn, ctx: AuthContext = Depends(get_auth), db: Session = Depends(get_db)) -> PlannedOut:
    count = db.scalar(select(func.count(PlannedPurchase.id)).where(PlannedPurchase.user_id == ctx.user.id))
    if count >= MAX_PLANNED:
        raise HTTPException(422, {"code": "too_many", "message": f"Limite de {MAX_PLANNED} compras planejadas atingido. Exclua alguma para cadastrar outra."})
    svc.check_inputs(db, ctx.user.id, body.total_amount, body.installments_count, body.category_id)
    p = PlannedPurchase(user_id=ctx.user.id, **body.model_dump())
    db.add(p)
    db.flush()
    db.refresh(p)
    out = _out(db, ctx.user.id, p)
    db.commit()
    return out


@router.get("/{pid}/analysis", response_model=AnalysisOut, summary="Impacto mês a mês no orçamento")
def analysis(pid: uuid.UUID, ctx: AuthContext = Depends(get_auth_synced), db: Session = Depends(get_db)):
    return svc.analyze_saved(db, ctx.user.id, svc.get(db, ctx.user.id, pid))


@router.patch("/{pid}", response_model=PlannedOut)
def update_planned(pid: uuid.UUID, body: PlannedUpdate, ctx: AuthContext = Depends(get_auth), db: Session = Depends(get_db)) -> PlannedOut:
    p = svc.get(db, ctx.user.id, pid)
    changes = body.model_dump(exclude_unset=True)
    for k, v in changes.items():
        if v is None and k != "notes":
            raise HTTPException(422, {"code": "validation_error", "message": "Campo obrigatório não pode ficar vazio."})
    svc.check_inputs(db, ctx.user.id, changes.get("total_amount", p.total_amount),
                     changes.get("installments_count", p.installments_count),
                     changes.get("category_id", p.category_id), allow_inactive_id=p.category_id)
    for k, v in changes.items():
        setattr(p, k, v)
    db.flush()
    db.expire(p, ["category"])
    out = _out(db, ctx.user.id, p)
    db.commit()
    return out


@router.delete("/{pid}", response_model=MessageOut)
def delete_planned(pid: uuid.UUID, ctx: AuthContext = Depends(get_auth), db: Session = Depends(get_db)) -> MessageOut:
    db.delete(svc.get(db, ctx.user.id, pid))
    db.commit()
    return MessageOut(message="Compra planejada excluída.")
