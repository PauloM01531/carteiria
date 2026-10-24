"""Contas recorrentes e suas ocorrências (previstas e pagas)."""
import uuid
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import AuthContext, get_auth
from app.db import get_db
from app.models import BillOccurrence, RecurringBill
from app.schemas import MessageOut
from app.schemas_cards import (
    AmountIn,
    BillCreate,
    BillOut,
    BillUpdate,
    OccurrenceList,
    OccurrenceOut,
    OccurrenceSummary,
    PayIn,
)
from app.services import bills as svc
from app.services.calendar import today

router = APIRouter(tags=["contas recorrentes"])


def _bill_out(b: RecurringBill) -> BillOut:
    return BillOut(
        id=b.id, name=b.name, amount_type=b.amount_type, expected_amount=b.expected_amount, category_id=b.category_id,
        category_name=b.category.name, frequency=b.frequency, due_day=b.due_day, start_date=b.start_date,
        end_date=b.end_date, active=b.active, notes=b.notes,
    )


def _occ_out(o: BillOccurrence, ref: date) -> OccurrenceOut:
    return OccurrenceOut(
        id=o.id, bill_id=o.bill_id, bill_name=o.bill.name, category_name=o.bill.category.name,
        amount_type=o.bill.amount_type, due_date=o.due_date, amount=o.amount,
        status=svc.occurrence_state(o, ref), paid_on=o.paid_on, transaction_id=o.transaction_id,
    )


@router.get("/bills", response_model=list[BillOut])
def list_bills(ctx: AuthContext = Depends(get_auth), db: Session = Depends(get_db)) -> list[BillOut]:
    rows = db.scalars(select(RecurringBill).where(RecurringBill.user_id == ctx.user.id)
                      .order_by(RecurringBill.active.desc(), RecurringBill.due_day, RecurringBill.name)).all()
    return [_bill_out(b) for b in rows]


@router.post("/bills", response_model=BillOut, status_code=201)
def create_bill(body: BillCreate, ctx: AuthContext = Depends(get_auth), db: Session = Depends(get_db)) -> BillOut:
    b = svc.create_bill(db, ctx.user.id, body.model_dump())
    out = _bill_out(b)
    db.commit()
    return out


@router.patch("/bills/{bill_id}", response_model=BillOut)
def update_bill(bill_id: uuid.UUID, body: BillUpdate, ctx: AuthContext = Depends(get_auth), db: Session = Depends(get_db)) -> BillOut:
    changes = body.model_dump(exclude_unset=True)
    for k, v in changes.items():
        if v is None and k not in ("end_date", "notes", "expected_amount"):
            raise HTTPException(422, {"code": "validation_error", "message": "Campo obrigatório não pode ficar vazio."})
    b = svc.update_bill(db, ctx.user.id, bill_id, changes)
    out = _bill_out(b)
    db.commit()
    return out


@router.delete("/bills/{bill_id}", response_model=MessageOut)
def delete_bill(bill_id: uuid.UUID, ctx: AuthContext = Depends(get_auth), db: Session = Depends(get_db)) -> MessageOut:
    svc.delete_bill(db, ctx.user.id, bill_id)
    db.commit()
    return MessageOut(message="Conta excluída. Pagamentos já registrados continuam nos lançamentos.")


@router.get("/bills/occurrences", response_model=OccurrenceList)
def occurrences(start: date, end: date, ctx: AuthContext = Depends(get_auth), db: Session = Depends(get_db)) -> OccurrenceList:
    if end < start or (end - start).days > 400:
        raise HTTPException(422, {"code": "invalid_period", "message": "Período inválido (máximo de 13 meses)."})
    rows = svc.list_occurrences(db, ctx.user.id, start, end)
    db.commit()  # grava as previsões geradas
    ref = today()
    items = [_occ_out(o, ref) for o in rows]
    pending = sum((o.amount or Decimal(0) for o in rows if o.status == "pending"), Decimal("0.00"))
    paid = sum((o.amount or Decimal(0) for o in rows if o.status == "paid"), Decimal("0.00"))
    return OccurrenceList(
        items=items,
        summary=OccurrenceSummary(pending_total=pending, paid_total=paid,
                                  overdue_count=sum(1 for i in items if i.status == "overdue")),
    )


@router.post("/bills/occurrences/{occ_id}/pay", response_model=OccurrenceOut)
def pay(occ_id: uuid.UUID, body: PayIn, ctx: AuthContext = Depends(get_auth), db: Session = Depends(get_db)) -> OccurrenceOut:
    o = svc.pay(db, ctx.user.id, occ_id, body.paid_on, body.amount, body.payment_method)
    out = _occ_out(o, today())
    db.commit()
    return out


@router.post("/bills/occurrences/{occ_id}/unpay", response_model=OccurrenceOut)
def unpay(occ_id: uuid.UUID, ctx: AuthContext = Depends(get_auth), db: Session = Depends(get_db)) -> OccurrenceOut:
    o = svc.unpay(db, ctx.user.id, occ_id)
    out = _occ_out(o, today())
    db.commit()
    return out


@router.patch("/bills/occurrences/{occ_id}", response_model=OccurrenceOut)
def set_amount(occ_id: uuid.UUID, body: AmountIn, ctx: AuthContext = Depends(get_auth), db: Session = Depends(get_db)) -> OccurrenceOut:
    o = svc.set_amount(db, ctx.user.id, occ_id, body.amount)
    out = _occ_out(o, today())
    db.commit()
    return out
