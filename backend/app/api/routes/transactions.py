"""Receitas e despesas. Exige usuário ativo; dono sempre vem da sessão."""
import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import AuthContext, get_auth
from app.db import get_db
from app.models import Transaction
from app.schemas import MessageOut
from app.schemas_finance import (
    Kind,
    PaymentMethod,
    Totals,
    TransactionCreate,
    TransactionOut,
    TransactionPage,
    TransactionUpdate,
    TxStatus,
)
from app.services import transactions as svc

router = APIRouter(tags=["lançamentos"])


def _out(tx: Transaction) -> TransactionOut:
    return TransactionOut(
        id=tx.id, kind=tx.kind, description=tx.description, amount=tx.amount, occurred_on=tx.occurred_on,
        category_id=tx.category_id, category_name=tx.category.name, payment_method=tx.payment_method,
        status=tx.status, notes=tx.notes, created_at=tx.created_at, updated_at=tx.updated_at,
    )


def _filters(
    start: date | None = None,
    end: date | None = None,
    kind: Kind | None = None,
    category_id: uuid.UUID | None = None,
    payment_method: PaymentMethod | None = None,
    status: TxStatus | None = None,
    q: str | None = Query(default=None, max_length=100),
) -> svc.TxFilters:
    if start and end and start > end:
        raise HTTPException(422, {"code": "invalid_period", "message": "A data inicial deve ser anterior à final."})
    return svc.TxFilters(start, end, kind, category_id, payment_method, status, q)


@router.get("/transactions", response_model=TransactionPage)
def list_transactions(
    f: svc.TxFilters = Depends(_filters),
    page: int = Query(default=1, ge=1, le=10_000),
    page_size: int = Query(default=50, ge=1, le=200),
    ctx: AuthContext = Depends(get_auth),
    db: Session = Depends(get_db),
) -> TransactionPage:
    rows, total = svc.list_transactions(db, ctx.user.id, f, page, page_size)
    return TransactionPage(
        items=[_out(t) for t in rows], total=total, page=page, page_size=page_size,
        totals=Totals(**svc.totals(db, ctx.user.id, f)),
    )


@router.get("/transactions/summary", response_model=Totals)
def summary(f: svc.TxFilters = Depends(_filters), ctx: AuthContext = Depends(get_auth), db: Session = Depends(get_db)) -> Totals:
    return Totals(**svc.totals(db, ctx.user.id, f))


@router.post("/transactions", response_model=TransactionOut, status_code=201)
def create_transaction(body: TransactionCreate, ctx: AuthContext = Depends(get_auth), db: Session = Depends(get_db)) -> TransactionOut:
    tx = svc.create(db, ctx.user.id, body.model_dump())
    out = _out(tx)
    db.commit()
    return out


@router.get("/transactions/{tx_id}", response_model=TransactionOut)
def get_transaction(tx_id: uuid.UUID, ctx: AuthContext = Depends(get_auth), db: Session = Depends(get_db)) -> TransactionOut:
    return _out(svc.get_owned(db, ctx.user.id, tx_id))


@router.patch("/transactions/{tx_id}", response_model=TransactionOut)
def update_transaction(
    tx_id: uuid.UUID, body: TransactionUpdate, ctx: AuthContext = Depends(get_auth), db: Session = Depends(get_db)
) -> TransactionOut:
    changes = body.model_dump(exclude_unset=True)
    for required in ("kind", "description", "amount", "occurred_on", "category_id", "payment_method", "status"):
        if required in changes and changes[required] is None:
            raise HTTPException(422, {"code": "validation_error", "message": "Campo obrigatório não pode ficar vazio."})
    tx = svc.update(db, ctx.user.id, tx_id, changes)
    out = _out(tx)
    db.commit()
    return out


@router.delete("/transactions/{tx_id}", response_model=MessageOut)
def delete_transaction(tx_id: uuid.UUID, ctx: AuthContext = Depends(get_auth), db: Session = Depends(get_db)) -> MessageOut:
    svc.delete(db, ctx.user.id, tx_id)
    db.commit()
    return MessageOut(message="Lançamento excluído.")
